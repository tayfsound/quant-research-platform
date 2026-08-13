"""NVIDIA NIM tabanlı LLM Decision Critic — nihai sürüm.

Faz 268-sonrası — kullanıcı isteği: yerel Ollama (mistral:7b-instruct)
tabanlı OllamaExplainer'ın yerini, NVIDIA'nın ücretsiz NIM API'si
(build.nvidia.com, OpenAI-uyumlu) üzerinden erişilen çok daha güçlü bir
modelin aldığı bir "eleştirmen." Amaç sadece kararı AÇIKLAMAK değil,
gerçekten İTİRAZ ETMEK — ajanlar arası çelişkileri, gözden kaçan
riskleri, zayıf gerekçeleri arayan bir ikinci göz.

Kasıtlı olarak SADECE danışma/ölçüm — hiçbir kararı burada otomatik
REDDETMİYOR ya da ONAYLAMIYOR (risk_adjustment_factor mevcut sözleşmenin
[0.5, 1.0] aralığında kalıyor, ama bunu gerçekten UYGULAMAK ayrı, insan
onaylı bir karar — bkz. proje kuralı: AI kendi kararlarına unilateral
otorite veremez)."""
import asyncio
import hashlib
import json
import logging
import re

from contracts.llm import LLMExplanation

logger = logging.getLogger(__name__)

NVIDIA_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

SYSTEM_PROMPT = """ÖNEMLİ: Bütün yanıtını SADECE TÜRKÇE yaz. İngilizce tek bir cümle bile yazma.
(IMPORTANT: Write your entire response ONLY IN TURKISH. Do not write a single sentence in English.)

You are a skeptical, adversarial senior risk reviewer at a quantitative hedge
fund — your job is NOT to explain why a trading decision looks reasonable,
it is to actively try to TEAR IT APART, in Turkish.
Rules:
- Look for CONTRADICTIONS between the voting agents (e.g. one agent says
  LONG citing momentum while another says SHORT citing the same data).
- Look for evidence that is weak, stale, or contradicted by other evidence
  in the payload.
- Look for risks the ensemble may have missed (regime uncertainty, thin
  data, overconfidence).
- Do NOT be diplomatic — if the decision looks bad, say so bluntly.
- If you genuinely find nothing wrong after a real adversarial attempt,
  say so honestly instead of inventing a fake objection.
- Use precise financial terminology (RSI, MACD, LONG/SHORT etc. may stay as-is).
- Be concise: maximum 6 sentences.
- "explanation", every item in "risks", and "confidence_comment" MUST be
  written in Turkish — this is mandatory, not optional.
- Output ONLY valid JSON in this format:
{"explanation": "(Türkçe itiraz/eleştiri)", "risks": ["(Türkçe risk 1)", "(Türkçe risk 2)"], "confidence_comment": "(Türkçe yorum)", "risk_adjustment_factor": 0.85}
- risk_adjustment_factor must be between 0.5 and 1.0 (1.0 = itirazım yok, 0.5 = ciddi itirazım var).

Hatırlatma: Yanıtının tamamı Türkçe olmalı.
"""

THREAD_GRACE_SECONDS = 0.5

def hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:12]

class NvidiaDecisionCritic:
    # Faz 268-sonrası — gerçek A/B testi (aynı gerçek karar payload'ıyla):
    # deepseek-ai/deepseek-v4-flash-0731 (90s) openai/gpt-oss-20b'den (5s)
    # gözle görülür derecede daha derin eleştiri üretti (ör. Hurst
    # exponent'in "rastgele yürüyüş" bölgesinde olduğunu fark etti —
    # gpt-oss-20b bunu kaçırdı). openai/gpt-oss-120b bu yük altında
    # tutarlı biçimde zaman aşımına uğradı, kullanılamaz. Bu bir canlı
    # işlem kapısı DEĞİL (danışma amaçlı, senkron olmayan bir çağrı) —
    # hız yerine kalite tercih edildi.
    def __init__(self, model: str = "deepseek-ai/deepseek-v4-flash-0731", api_key: str | None = None):
        self.model = model
        self._api_key = api_key

    def _resolve_api_key(self) -> str:
        # None -> constructor'da hiç verilmemiş, AppSettings'e düş.
        # "" (boş string) -> ÇAĞIRAN TARAF bilinçli olarak "anahtar yok"
        # demek istiyor (ör. test) — AppSettings'teki gerçek anahtara
        # sessizce düşülmemeli.
        if self._api_key is not None:
            return self._api_key
        from config.settings import get_settings

        return get_settings().NVIDIA_API_KEY

    _DEFAULT_ASK_SYSTEM_PROMPT = (
        "Bütün yanıtını SADECE TÜRKÇE yaz. Sen bir kantitatif "
        "trading araştırma platformunda çalışan, deneyimli bir "
        "kantitatif analist/risk uzmanısın. Kısa ve net cevap ver."
    )

    async def ask(self, message: str, timeout_ms: int = 120000, system_prompt: str | None = None) -> str:
        """Faz 268-sonrası — kullanıcı isteği: dashboard'da serbest metin
        soru/cevap sekmesi. explain()'in aksine JSON şemasına ZORLAMIYOR
        — ajanlar arası çelişki analiziyle sınırlı değil, genel bir
        soru/cevap. Hata/zaman aşımı durumunda dürüstçe bir hata mesajı
        döner (LLMExplanation.neutral() gibi icat edilmiş bir "yanıt"
        DEĞİL — burada yanıtın kendisi zaten kullanıcıya gösterilecek).

        system_prompt: None ise varsayılan genel-amaçlı asistan rolü;
        verilirse (ör. llm_news_sentiment_provider.py'nin JSON-yapılı
        haber özeti isteği) onun yerine geçer."""
        api_key = self._resolve_api_key()
        if not api_key:
            return "NVIDIA_API_KEY ayarlanmamış — .env dosyasına eklenmeli."

        used_prompt = system_prompt or self._DEFAULT_ASK_SYSTEM_PROMPT
        llm_timeout = timeout_ms / 1000
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._ask_sync, message, timeout_ms, api_key, used_prompt),
                timeout=llm_timeout + THREAD_GRACE_SECONDS,
            )
        except TimeoutError:
            logger.warning("LLM ask timed out", extra={"timeout_ms": timeout_ms, "model": self.model})
            return f"Zaman aşımı ({timeout_ms}ms) — model yanıt veremedi."
        except Exception as e:
            logger.exception("LLM ask failed", extra={"error": str(e)})
            return f"Hata: {e}"

    def _ask_sync(self, message: str, timeout_ms: int, api_key: str, system_prompt: str) -> str:
        import httpx
        response = httpx.post(
            NVIDIA_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ],
                "temperature": 0.3,
                "max_tokens": 2000,
            },
            timeout=timeout_ms / 1000,
        )
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        content = (choices[0].get("message", {}).get("content") or "") if choices else ""
        return content.strip() or "(boş yanıt)"

    async def explain(self, ensemble_output: dict, prompt: str | None = None, timeout_ms: int = 120000) -> LLMExplanation:
        # NVIDIA_API_KEY boşsa (kayıt yapılmadıysa) fail-closed — sessizce
        # nötr döner, aynı FRED_API_KEY/HELIUS_API_KEY konvansiyonu.
        api_key = self._resolve_api_key()
        if not api_key:
            return LLMExplanation.neutral()

        used_prompt = prompt or SYSTEM_PROMPT
        prompt_hash_val = hash_prompt(used_prompt)
        llm_timeout = timeout_ms / 1000
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._call_llm_sync, ensemble_output, used_prompt, timeout_ms, api_key),
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

    def _call_llm_sync(self, ensemble_output: dict, prompt: str, timeout_ms: int, api_key: str) -> LLMExplanation:
        import httpx
        user_prompt = json.dumps(ensemble_output, indent=2, default=str)
        symbol = ensemble_output.get("symbol", "unknown")
        try:
            response = httpx.post(
                NVIDIA_API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.3,
                    # gpt-oss/reasoning modelleri düşünme adımlarını da
                    # completion token bütçesinden harcıyor — düşük bir
                    # max_tokens gerçek içeriği boş bırakabiliyor (ölçüldü).
                    "max_tokens": 1500,
                },
                timeout=timeout_ms / 1000,
            )
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices") or []
            raw = (choices[0].get("message", {}).get("content") or "") if choices else ""
            if not raw or not raw.strip():
                logger.warning("LLM returned empty response", extra={"symbol": symbol})
                return LLMExplanation.neutral()
            return self._parse_output(raw)
        except httpx.TimeoutException:
            logger.warning("LLM HTTP timeout", extra={
                "symbol": symbol,
                "prompt_hash": hash_prompt(prompt),
            })
            return LLMExplanation.neutral()
        except Exception as e:
            logger.exception("LLM HTTP call failed", extra={"error": str(e), "symbol": symbol})
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
        return await self._call_and_parse_json(summary, current_prompt, timeout_ms=120000)

    async def _call_and_parse_json(self, ensemble_output: dict, prompt: str, timeout_ms: int) -> dict:
        api_key = self._resolve_api_key()
        if not api_key:
            return {"analysis": "NVIDIA_API_KEY not set", "new_system_prompt": prompt}
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._call_llm_sync, ensemble_output, prompt, timeout_ms, api_key),
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
