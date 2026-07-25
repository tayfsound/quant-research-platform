"""Meta‑Optimizer — filelock, DI."""
import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path

from filelock import FileLock

from contracts.llm import LLMExplainerPort
from contracts.repositories import ExperimentLogRepository
from meta_optimizer.ab_runner import ABTestRunner
from meta_optimizer.analyzer import PromptAnalyzer
from meta_optimizer.collector import ExperimentLog

CURRENT_PROMPT = """You are a world-class quantitative hedge fund analyst..."""

class MetaOptimizer:
    def __init__(self, repository: ExperimentLogRepository, explainer: LLMExplainerPort):
        self.repository = repository
        self.analyzer = PromptAnalyzer(repository, explainer)
        self.current_prompt = CURRENT_PROMPT
        self.runner: ABTestRunner | None = None

    def on_trade_completed(self, log_data: dict):
        log = ExperimentLog(**log_data)
        self.repository.record(log)

    async def trigger_analysis(self):
        suggestion = await self.analyzer.analyze_and_suggest(self.current_prompt)
        new_prompt = suggestion.get("new_system_prompt", self.current_prompt)
        if new_prompt != self.current_prompt:
            self.runner = ABTestRunner(self.current_prompt, new_prompt)
            self.runner.start()

    async def finalize_ab_test(self):
        if not self.runner:
            return
        evaluation = self.runner.evaluate()
        self.runner.save_results()
        if evaluation["verdict"] == "accept_b":
            self._save_prompt_registry_locked(evaluation)
        self.runner = None

    def _save_prompt_registry_locked(self, evaluation: dict):
        registry_path = Path("prompt_registry.json")
        lock_path = Path("prompt_registry.lock")
        with FileLock(lock_path, timeout=5):
            registry = []
            if registry_path.exists():
                with suppress(json.JSONDecodeError):
                    registry = json.loads(registry_path.read_text())
            registry.append({
                "timestamp": evaluation.get("timestamp", ""),
                "candidate_prompt": self.runner.prompt_b if self.runner else "",
                "evaluation": evaluation,
                "status": "pending_approval",
            })
            fd, tmp_path = tempfile.mkstemp(dir=registry_path.parent, prefix="prompt_registry.")
            with os.fdopen(fd, "w") as f:
                json.dump(registry, f, indent=2)
            os.replace(tmp_path, registry_path)
        print("📌 Yeni prompt adayı kaydedildi (onay bekliyor).")
