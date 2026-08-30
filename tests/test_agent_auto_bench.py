"""Auto-bench: a domain with a genuinely poor REAL track record (was_correct-
based, from AgentMemory — not raw confidence, bkz. agents/source_
reliability_agent.py) has its vote weight genuinely reduced — not a
"stress" metaphor, a real performance_weight drop that effective_influence
(intrinsic_trust * performance_weight) propagates into a much smaller
actual influence on the belief.

Faz 370-devam — KRİTİK canlı olay (kullanıcı teşhisi): performance_weight
artık literal 0.0'a DEĞİL düşüyor — tam susturma kendi kendini besleyen
bir kilitlenme döngüsüne açıktı ("son 20 kötü -> tamamen sustur -> ajan
hiç etkilemediği için sonraki kararlar onu güncellemiyor -> uzun süre
sessiz kalabiliyor"). Ajan hâlâ konuşuyor, sadece bağırmıyor. Ayrıca üç
pencerenin (20/100/500) ağırlıklı ortalaması + histerezis (bench/unbench
için FARKLI eşikler) kullanılıyor — recover TEK bir iyi seriyle değil,
UNBENCH_THRESHOLD'u (0.55, BENCH_THRESHOLD'tan [0.35] yüksek) aşan bir
toparlanmayla olur.

Faz 381 — kullanıcı bulgusu (sistem genelinde 642/642 karar reddi):
DÜZ bir floor (MIN_INFLUENCE=0.1) da sorunluydu — eşiğin AZ altındaki
("marjinal" benched, ör. bu dosyanın 15-kayıtlık senaryosu) bir ajan ile
KATASTROFİK derecede kötü (source_reliability→0) bir ajan AYNI floor'a
düşüyordu. Artık reliability açığına ORANTILI bastırılıyor (bkz.
services/agent_reliability_weighting.py) — marjinal vakalar artık MIN_
INFLUENCE'tan belirgin şekilde yüksek bir ağırlık alıyor, katastrofik
vakalar hâlâ eski floor'a yakın bastırılıyor."""
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

    assert technical.performance_weight < 1.0
    assert technical.performance_weight > 0.0
    assert technical.effective_influence > 0.0
    assert any("benched" in c.lower() for c in technical.caveats)

    # Faz 376 — kullanıcı isteği: "decision decomposition" için ham/
    # kalibre edilmiş/güvenilirlik/rejim/itiraz zincirinin YAPILANDIRILMIŞ
    # (serbest-metin caveats DEĞİL) olarak da kayıtlı olması.
    bench_step = next(a for a in technical.weight_adjustments if a["step"] == "benching_floor")
    assert bench_step["before"] > bench_step["after"]
    assert bench_step["after"] > 0.0


def test_marginally_benched_domain_is_far_less_suppressed_than_old_flat_floor(tmp_path):
    """Faz 381 — asıl düzeltilen davranış: 15 kayıtlık (marjinal kötü,
    katastrofik değil) bir geçmiş, eski sistemde de yeni sistemde de
    benched'e düşüyor, ama artık DÜZ MIN_INFLUENCE (0.1) floor'una
    SAPLANMIYOR — reliability açığının gerçek büyüklüğüne orantılı,
    belirgin şekilde daha yüksek bir ağırlık alıyor."""
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

    assert any("benched" in c.lower() for c in technical.caveats)
    assert technical.performance_weight > 5 * SourceReliabilityAgent.MIN_INFLUENCE


def test_catastrophically_unreliable_domain_is_still_strongly_suppressed(tmp_path):
    """Faz 381 — gerçekten kötü bir ajan (üç pencerenin de dolduğu,
    sürekli yanlış bir geçmiş) hâlâ GÜÇLÜ şekilde bastırılmalı — "marjinal
    olanlar artık haksız yere susturulmuyor" ilkesi, "gerçek kötü ajanlar
    hâlâ susturuluyor" ilkesini bozmuyor. (source_reliability, Beta-prior
    yumuşatması nedeniyle asla tam 0'a inmiyor — bu yüzden eski MIN_
    INFLUENCE=0.1 floor'unun BİREBİR aynısı değil, ama başlangıç 1.0'dan
    belirgin, ağır bir düşüş.)"""
    orchestrator = CouncilOrchestrator(AgentRegistry.create_default())
    memory = AgentMemory(storage_path=str(tmp_path))
    _seed(memory, "technical", 600, was_correct=False)  # 20/100/500 pencerelerinin ÜÇÜNÜ de dolduracak kadar
    orchestrator.reliability_annotator.agent.memory = memory

    ctx = {AgentDomain.TECHNICAL: TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs",
        ema_alignment="bullish_aligned", volume_confirmation=True,
        adx=30.0, di_plus=30.0, di_minus=10.0,
    )}
    _, opinions = orchestrator.deliberate(ctx)
    technical = next(o for o in opinions if o.domain == AgentDomain.TECHNICAL)

    assert any("benched" in c.lower() for c in technical.caveats)
    assert technical.performance_weight < 0.4


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
    benched_technical = next(o for o in opinions if o.domain == AgentDomain.TECHNICAL)
    assert benched_technical.performance_weight < 1.0
    assert any("benched" in c.lower() for c in benched_technical.caveats)

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
