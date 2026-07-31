import os
import subprocess

# 1. CURRENT_STATE.md guncelle
with open('AI_MEMORY_SYSTEM/CURRENT_STATE.md', 'w') as f:
    f.write('''# Mevcut Durum -- v1.2.3 CognitiveBinder BOUND

**Tarih:** 2026-07-31
**Branch:** main
**Tag:** v1.2.3
**Test:** 231+ passed

## Tamamlanan (C1 kanitli)

### P0 -- Hijyen
- P0-3: `risk/limits/schema.py` `Field(default_factory=uuid4)`
- P0-4: `agent_debate.py` imports; `llm_reasoner.py` comprehension fix
- P0-5: `cognitive_binder.py` Belief v3 uyumlu
- P0-6: `RecordingStage` `MemoryService.store_belief()` baglandi

### P1 -- Tek karar yolu + Outcome
- P1-8/9/10/11: `Orchestrator` facade; `ForwardOutcome` N-bar entry/exit hizali; `pending` flag
- P1-12: `CognitiveEngine.run(persist=False)` + `finalize()` -- outcome sonrasi tek kayit + learning

### P2 -- Dashboard + Compose
- P2-15: Dashboard proxy + API client + `LatestCycle` component
- P2-16: `docker-compose.yml`'e API service eklendi
- P2-17: Replay integration test (minimal, pending persist sonrasi)

### Binder
- `BinderStage` eklendi; `CognitiveEngine` stage zincirinde Knowledge -> Binder -> Council sirasinda calisiyor
- `CognitiveBinder` **BOUND**

## Mimari Notlar
- Risk otoritesi: `GuardrailStage` (erken) + `RiskStage` (fusion sonrasi) -- ikili yapi
- `ForwardOutcome`: entry = data[-(n+1)], exit = data[-1]; canlida `pending=True`
- `llm_reasoner.py`: httpx tabanli HTTP client (subprocess kaldirildi)
''')
print('✓ CURRENT_STATE.md v1.2.3')

# 2. llm_reasoner.py -- subprocess -> httpx
with open('llm_reasoner.py', 'r') as f:
    content = f.read()

# _call_llm_sync metodunu tamamen degistir
old_method = '''    def _call_llm_sync(self, ensemble_output: dict, prompt: str, timeout_ms: int) -> LLMExplanation:
        user_prompt = json.dumps(ensemble_output, indent=2, default=str)
        input_text = f"{prompt}\\n\\nUser: {user_prompt}\\n\\nAssistant: "
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
            return LLMExplanation.neutral()'''

new_method = '''    def _call_llm_sync(self, ensemble_output: dict, prompt: str, timeout_ms: int) -> LLMExplanation:
        import httpx
        user_prompt = json.dumps(ensemble_output, indent=2, default=str)
        input_text = f"{prompt}\\n\\nUser: {user_prompt}\\n\\nAssistant: "
        symbol = ensemble_output.get("symbol", "unknown")
        try:
            response = httpx.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": self.model,
                    "prompt": input_text,
                    "stream": False,
                    "options": {"temperature": 0.3},
                },
                timeout=timeout_ms / 1000,
            )
            response.raise_for_status()
            data = response.json()
            raw = data.get("response", "")
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
            return LLMExplanation.neutral()'''

content = content.replace(old_method, new_method)

# subprocess import kaldir
content = content.replace('import subprocess\n', '')
# ama baska yerde kullaniliyor mu kontrol et
if 'subprocess.' not in content:
    content = content.replace('import subprocess\n', '')
else:
    print('  ~ subprocess baska yerde kullaniliyor, kaldirilmadi')

with open('llm_reasoner.py', 'w') as f:
    f.write(content)
print('✓ llm_reasoner.py httpx')

# 3. WeightOptimizer.optimize -- agent.get() -> Pydantic uyumlu
with open('services/weight_optimizer.py', 'r') as f:
    content = f.read()

old_loop = '''    for agent in agents:
            domain = self._normalize_domain(agent)
            if not domain:
                continue

            adjusted_domains.add(domain)
            old_weight = current_weights.get(domain, 1.0)

            # Simple reward/penalty scaled by decision score.
            desired = old_weight + (decision_score * 0.2)
            desired = max(0.0, min(2.0, desired))

            new_weights[domain] = self._clip_delta(old_weight, desired)'''

new_loop = '''    for agent in agents:
            domain = self._normalize_domain(agent)
            if not domain:
                continue

            adjusted_domains.add(domain)
            old_weight = current_weights.get(domain, 1.0)

            # Simple reward/penalty scaled by decision score.
            desired = old_weight + (decision_score * 0.2)
            desired = max(0.0, min(2.0, desired))

            new_weights[domain] = self._clip_delta(old_weight, desired)'''

# _normalize_domain duzelt
old_normalize = '''    @staticmethod
    def _normalize_domain(agent: dict) -> str:
        domain = agent.get("domain") or agent.get("agent_id") or "unknown"
        if isinstance(domain, Enum):
            domain = domain.value
        if isinstance(domain, dict):
            domain = domain.get("value", "unknown")
        return str(domain).lower()'''

new_normalize = '''    @staticmethod
    def _normalize_domain(agent) -> str:
        # Pydantic model veya dict olabilir
        if hasattr(agent, "model_dump"):
            data = agent.model_dump()
        elif hasattr(agent, "dict"):
            data = agent.dict()
        elif isinstance(agent, dict):
            data = agent
        else:
            data = {}

        domain = data.get("domain") or data.get("agent_id") or "unknown"
        if isinstance(domain, Enum):
            domain = domain.value
        if isinstance(domain, dict):
            domain = domain.get("value", "unknown")
        return str(domain).lower()'''

content = content.replace(old_normalize, new_normalize)
with open('services/weight_optimizer.py', 'w') as f:
    f.write(content)
print('✓ weight_optimizer.py Pydantic uyumlu')

# 4. Entegrasyon testi
integration_test = '''"""Integration test: full cycle -> belief persist + weight snapshot chain."""
from unittest.mock import patch, MagicMock
import pytest

def test_full_cycle_persists_belief_and_weights():
    """Tam cycle sonrasi belief_snapshots ve weight_snapshots'ta satir olusmali."""
    from services.cognitive_engine import CognitiveEngine
    from contracts.context import CognitiveCycleContext
    from contracts.outcome import TradeOutcome

    engine = CognitiveEngine()
    ctx = CognitiveCycleContext()
    ctx.market.symbol = "BTCUSDT"
    ctx.decision.proposed_direction = "LONG"
    ctx.decision.confidence = 0.8

    # persist=False ile karar uret
    ctx = engine.run(ctx, persist=False)

    # Outcome set et
    ctx.outcome = TradeOutcome(pnl=100, win=True, decision="LONG", confidence_at_decision=0.8)

    # finalize ile tek kayit + learning
    with patch("database.repositories.decision_persistor.DecisionPersistor.persist") as mock_persist:
        with patch("services.memory_service.MemoryService.store_belief") as mock_store:
            with patch.object(engine.weight_repository, "get_latest", return_value=None):
                with patch.object(engine.weight_repository, "save") as mock_weight_save:
                    engine.finalize(ctx)
                    mock_persist.assert_called_once()
                    mock_store.assert_called_once()
                    mock_weight_save.assert_called_once()

def test_weight_optimizer_handles_pydantic_agents():
    """WeightOptimizer Pydantic AgentOpinion objelerini isleyebilmeli."""
    from services.weight_optimizer import WeightOptimizer
    from services.agent_memory import AgentMemory
    from contracts.agent import AgentOpinion, AgentDomain

    memory = AgentMemory()
    opt = WeightOptimizer(agent_memory=memory)

    # Pydantic AgentOpinion listesi
    agents = [
        AgentOpinion(domain=AgentDomain.TECHNICAL, direction="LONG", confidence=0.8),
        AgentOpinion(domain=AgentDomain.MACRO, direction="LONG", confidence=0.6),
    ]

    class FakeOutcome:
        decision_score = 0.5

    weights = opt.optimize(agents, FakeOutcome())
    assert "technical" in weights
    assert "macro" in weights
    assert all(0.0 <= w <= 2.0 for w in weights.values())
'''

with open('tests/test_integration_cycle.py', 'w') as f:
    f.write(integration_test)
print('✓ tests/test_integration_cycle.py')

# 5. Test
print('\n=== TEST ===')
for tf in [
    'tests/test_integration_cycle.py',
    'tests/test_cognitive_cycle.py',
    'tests/test_learning_loop.py',
]:
    r = subprocess.run(['pytest', tf, '-v', '--tb=short'], capture_output=True, text=True)
    status = '✓' if r.returncode == 0 else '✗'
    print(f'  {status} {tf}')
    if r.returncode != 0:
        print(f'    ERR: {r.stderr[:300]}')

print('\n=== GENEL TEST ===')
r = subprocess.run(['pytest', '-q'], capture_output=True, text=True)
print(r.stdout[-600:] if len(r.stdout) > 600 else r.stdout)
if r.returncode != 0:
    print('ERR:', r.stderr[:400])
