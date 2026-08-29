"""Auto-bench: a domain with a genuinely poor REAL track record (was_correct-
based, from AgentMemory — not raw confidence, bkz. agents/source_
reliability_agent.py) has its vote weight genuinely reduced — not a
"stress" metaphor, a real performance_weight drop that effective_influence
(intrinsic_trust * performance_weight) propagates into a much smaller
actual influence on the belief.

Faz 370-devam — KRİTİK canlı olay (kullanıcı teşhisi): performance_weight
artık literal 0.0'a DEĞİL, MIN_INFLUENCE'a (0.1) düşüyor — tam susturma
kendi kendini besleyen bir kilitlenme döngüsüne açıktı ("son 20 kötü ->
tamamen sustur -> ajan hiç etkilemediği için sonraki kararlar onu
güncellemiyor -> uzun süre sessiz kalabiliyor"). Ajan hâlâ konuşuyor
(küçük ağırlıkla), sadece bağırmıyor. Ayrıca artık üç pencerenin (20/100/
500) ağırlıklı ortalaması + histerezis (bench/unbench için FARKLI eşikler)
kullanılıyor — recover TEK bir iyi seriyle değil, UNBENCH_THRESHOLD'u
(0.55, BENCH_THRESHOLD'tan [0.35] yüksek) aşan bir toparlanmayla olur."""
from agents.registry import AgentRegistry
from agents.source_reliability_agent import SourceReliabilityAgent
from contracts.agent import AgentDomain
from contracts.agent_performance import AgentPerformanceRecord
from contracts.technical import TechnicalContext
from services.agent_memory import AgentMemory
from services.council_orchestrator import CouncilOrchestrator


def _seed(memory: AgentMemory, domain: str, n: int, was_correct: bool) -> None:
    for _ in range(n):
        memory.record(AgentPerformanceRecord(
            agent_domain=domain, direction="LONG", confidence=0.8, was_correct=was_correct,
        ))


def test_persistently_wrong_domain_gets_benched_and_reduced_not_zeroed(tmp_path):
    orchestrator = CouncilOrchestrator(AgentRegistry.create_default())
    memory = AgentMemory(storage_path=str(tmp_path))
    _seed(memory, "technical", 15, was_correct=False)
    orchestrator.reliability_annotator.agent.memory = memory

    ctx = {AgentDomain.TECHNICAL: TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs",
        ema_alignment="bullish_aligned", volume_confirmation=True,
        adx=30.0, di_plus=30.0, di_minus=10.0,
    )}
    _, opinions = orchestrator.deliberate(ctx)
    technical = next(o for o in opinions if o.domain == AgentDomain.TECHNICAL)

    assert technical.performance_weight == SourceReliabilityAgent.MIN_INFLUENCE
    assert technical.performance_weight > 0.0
    assert technical.effective_influence > 0.0
    assert any("benched" in c.lower() for c in technical.caveats)


def test_benched_domain_recovers_after_real_correct_track_record(tmp_path):
    orchestrator = CouncilOrchestrator(AgentRegistry.create_default())
    memory = AgentMemory(storage_path=str(tmp_path))
    _seed(memory, "technical", 15, was_correct=False)
    orchestrator.reliability_annotator.agent.memory = memory

    ctx = {AgentDomain.TECHNICAL: TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs",
        ema_alignment="bullish_aligned", volume_confirmation=True,
        adx=30.0, di_plus=30.0, di_minus=10.0,
    )}
    _, opinions = orchestrator.deliberate(ctx)
    assert next(o for o in opinions if o.domain == AgentDomain.TECHNICAL).performance_weight == SourceReliabilityAgent.MIN_INFLUENCE

    # Gerçek, sürekli isabetli sonuçlar birikince — genuine recovery.
    # UNBENCH_THRESHOLD (histerezis) daha yüksek bir bar olduğu için 15
    # kötü + 20 iyi karışık geçmişi net şekilde geçecek kadar güçlü bir
    # seri gerekiyor.
    _seed(memory, "technical", 20, was_correct=True)
    _, opinions = orchestrator.deliberate(ctx)

    technical = next(o for o in opinions if o.domain == AgentDomain.TECHNICAL)
    assert technical.performance_weight == 1.0
    assert not any("benched" in c.lower() for c in technical.caveats)


def test_insufficient_real_history_is_not_benched(tmp_path):
    """Yeni bir domain'in (henüz gerçek kapanmış işlem geçmişi olmayan)
    fail-closed davranışı: nötr, tam ağırlık — cezalandırılmıyor."""
    orchestrator = CouncilOrchestrator(AgentRegistry.create_default())
    orchestrator.reliability_annotator.agent.memory = AgentMemory(storage_path=str(tmp_path))

    ctx = {AgentDomain.TECHNICAL: TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs",
        ema_alignment="bullish_aligned", volume_confirmation=True,
        adx=30.0, di_plus=30.0, di_minus=10.0,
    )}
    _, opinions = orchestrator.deliberate(ctx)
    technical = next(o for o in opinions if o.domain == AgentDomain.TECHNICAL)

    assert technical.performance_weight == 1.0
    assert not any("benched" in c.lower() for c in technical.caveats)
