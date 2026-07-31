"""Ollama tabanlı LLM explainer — nihai sürüm."""
import asyncio
import hashlib
import json
import logging
import re
import subprocess

from contracts.llm import LLMExplanation

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a world-class quantitative hedge fund analyst with 20 years of experience.
Your job is to explain trading decisions made by an AI ensemble system.
Rules:
- Explain WHY the decision was made based on the data provided.
- Point out any inconsistencies or risks you see.
- Use precise financial terminology.
- Be concise: maximum 5 sentences.
- If the decision looks dangerous, say so clearly.
- Output ONLY valid JSON in this format:
{"explanation": "...", "risks": ["risk1", "risk2"], "confidence_comment": "...", "risk_adjustment_factor": 0.85}
- risk_adjustment_factor must be between 0.5 and 1.0.
"""

THREAD_GRACE_SECONDS = 0.5

def hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:12]

class OllamaExplainer:
    def __init__(self, model: str = "mistral:7b-instruct-v0.3-q4_K_M"):
        self.model = model

    async def explain(self, ensemble_output: dict, prompt: str | None = None, timeout_ms: int = 500) -> LLMExplanation:
        used_prompt = prompt or SYSTEM_PROMPT
        prompt_hash_val = hash_prompt(used_prompt)
        llm_timeout = timeout_ms / 1000
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._call_llm_sync, ensemble_output, used_prompt, timeout_ms),
                timeout=llm_timeout + THREAD_GRACE_SECONDS,
            )
        except TimeoutError:
            logger.warning("LLM explain timed out", extra={
                "timeout_ms": timeout_ms,
                "symbol": ensemble_output.get("symbol"),
                "trade_id": ensemble_output.get("trade_id"),
                "model": self.model,
                "prompt_hash": prompt_hash_val,
            })
            return LLMExplanation.neutral()
        except Exception as e:
            logger.exception("LLM explain failed", extra={
                "error": str(e),
                "symbol": ensemble_output.get("symbol"),
                "prompt_hash": prompt_hash_val,
            })
            return LLMExplanation.neutral()

    def _call_llm_sync(self, ensemble_output: dict, prompt: str, timeout_ms: int) -> LLMExplanation:
        user_prompt = json.dumps(ensemble_output, indent=2, default=str)
        input_text = f"{prompt}\n\nUser: {user_prompt}\n\nAssistant: "
        symbol = ensemble_output.get("symbol", "unknown")
        try:
            process = subprocess.Popen(
                ["ollama", "run", self.model],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                stdout, stderr = process.communicate(input=input_text, timeout=timeout_ms / 1000)
                if stderr:
                    logger.warning("LLM stderr", extra={
                        "stderr": stderr.strip()[:200],
                        "symbol": symbol,
                        "model": self.model,
                    })
            except subprocess.TimeoutExpired:
                logger.warning("LLM process timed out, killing PID", extra={
                    "pid": process.pid,
                    "symbol": symbol,
                    "prompt_hash": hash_prompt(prompt),
                })
                process.kill()
                process.wait()
                return LLMExplanation.neutral()

            if process.returncode != 0:
                logger.error("LLM process exited non-zero", extra={
                    "returncode": process.returncode,
                    "stderr": stderr.strip()[:200],
                    "symbol": symbol,
                })
                return LLMExplanation.neutral()

            if not stdout or not stdout.strip():
                logger.warning("LLM returned empty stdout", extra={"symbol": symbol})
                return LLMExplanation.neutral()

            return self._parse_output(stdout)

        except Exception as e:
            logger.exception("LLM call failed", extra={"error": str(e), "symbol": symbol})
            return LLMExplanation.neutral()

    def _parse_output(self, raw: str) -> LLMExplanation:
        raw = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', raw)
        start = raw.find('{')
        if start != -1:
            raw = raw[start:]
        try:
            decoder = json.JSONDecoder()
            data, _ = decoder.raw_decode(raw)
        except json.JSONDecodeError:
            logger.warning("JSON parse failed", extra={"raw_preview": raw[:200]})
            return LLMExplanation(
                explanation=raw[:500],
                risks=[],
                confidence_comment="JSON parse failed",
                risk_adjustment_factor=1.0,
            )

        return LLMExplanation(
            explanation=data.get("explanation", ""),
            risks=data.get("risks", []),
            confidence_comment=data.get("confidence_comment", ""),
            risk_adjustment_factor=data.get("risk_adjustment_factor", 1.0),
        )

    async def analyze_logs(self, logs: list[dict], current_prompt: str) -> dict:
        if not logs:
            return {"analysis": "No logs", "new_system_prompt": current_prompt}
        total = len(logs)
        wins = [trade_log for trade_log in logs if trade_log.get("outcome", {}).get("pnl", 0) > 0]
        losses = [trade_log for trade_log in logs if trade_log.get("outcome", {}).get("pnl", 0) <= 0]
        win_rate = len(wins) / total if total > 0 else 0.0
        summary = {
            "task": "analyze_logs",
            "total_trades": total,
            "win_rate": f"{win_rate:.1%}",
            "avg_confidence": f"{sum(trade_log.get('confidence', 0) for trade_log in logs) / total:.2f}" if total > 0 else "0.0",
            "current_prompt": current_prompt,
            "recent_trades": logs[-10:],
            "best_trades": sorted(wins, key=lambda trade_log: trade_log.get("outcome", {}).get("pnl", 0), reverse=True)[:5],
            "worst_trades": sorted(losses, key=lambda trade_log: trade_log.get("outcome", {}).get("pnl", 0))[:5],
        }
        return await self._call_and_parse_json(summary, current_prompt, timeout_ms=15000)

    async def _call_and_parse_json(self, ensemble_output: dict, prompt: str, timeout_ms: int) -> dict:
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._call_llm_sync, ensemble_output, prompt, timeout_ms),
                timeout=timeout_ms / 1000 + THREAD_GRACE_SECONDS,
            )
            decoder = json.JSONDecoder()
            raw = result.explanation
            start = raw.find('{')
            if start != -1:
                raw = raw[start:]
            data, _ = decoder.raw_decode(raw)
            return data if isinstance(data, dict) else {}
        except (TimeoutError, json.JSONDecodeError, Exception):
            return {"analysis": "LLM call failed", "new_system_prompt": prompt}
