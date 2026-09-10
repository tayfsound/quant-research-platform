"""Faz 485 — karar ile aksiyon arasına 123 sembollük bekleme konulamaz.

Kullanıcı tespiti (2026-09-10): "Bir döngü bu kadar uzun sürerse sağlıklı
işlem yapamaz ki zaten. AI şu an bir pozisyon önerisinde bulundu diyelim
40-50 dk sonra şartların değişmiş olma olasılığı çok yüksek... karar verip
40-50 dk sonra aksiyon alırsa sürekli yanlış şeyler yapacak."

Ölçümle doğrulandı ve gecikmeden DAHA KÖTÜ çıktı: `finalize_proposal`
fiyatı yeniden ÇEKMİYOR, `propose` anındaki `data[-1].close`'u kullanıyor.
Eski yapı tüm watchlist'i propose edip sonra finalize ettiği için ilk
sembol 25-90 dakika BAYAT fiyatla açılıyordu; stop/hedef de o bayat
fiyattan türetiliyordu.

Bu test yapısal değişmezi kilitliyor: her sembolün finalize'ı, bir
sonraki sembolün propose'undan ÖNCE olmalı.
"""
from typing import Any

from services.orchestrator import CognitiveOrchestrator


class _Recorder(CognitiveOrchestrator):
    """propose/finalize çağrı SIRASINI kaydeden ince bir alt sınıf.
    Gerçek ağ/DB'ye hiç gitmiyor — sadece sıralama değişmezini ölçüyor."""

    def __init__(self, symbols: list[str]):
        self.calls: list[tuple[str, str]] = []
        self._symbols = symbols

    def propose(self, symbol: str) -> dict | None:
        self.calls.append(("propose", symbol))
        return {"symbol": symbol, "direction": "NEUTRAL", "ctx": _FakeCtx(), "data": [_FakeBar()]}

    propose_medium_term = propose

    def finalize_proposal(self, proposal: dict, seed: int = 42) -> dict[str, Any]:
        self.calls.append(("finalize", proposal["symbol"]))
        return {"symbol": proposal["symbol"], "direction": "NEUTRAL"}

    def _apply_portfolio_fusion(self, directional: dict) -> None:  # pragma: no cover
        self.calls.append(("fusion", next(iter(directional))))


class _FakeBar:
    close = 100.0


class _FakeDecision:
    final_size = 0.0


class _FakeCtx:
    def __init__(self):
        self.decision = _FakeDecision()


def _interleaving_is_per_symbol(calls: list[tuple[str, str]], symbols: list[str]) -> bool:
    """propose(A), finalize(A), propose(B), finalize(B), ... deseni."""
    expected = []
    for s in symbols:
        expected += [("propose", s), ("finalize", s)]
    return [c for c in calls if c[0] in ("propose", "finalize")] == expected


def test_short_term_cycle_finalizes_each_symbol_before_proposing_the_next():
    symbols = ["AAAUSDT", "BBBUSDT", "CCCUSDT"]
    orch = _Recorder(symbols)

    # macro/benched shadow tracker'ları gerçek ağ çağrısı yapmasın diye
    # devre dışı bırakmak gerekmiyor: propose() sahte bir ctx döndürüyor ve
    # tracker'lar kendi içlerinde hatayı sessizce yutuyor — yine de sıra
    # kaydı etkilenmiyor.
    orch.data_provider = None
    orch.memory = type("M", (), {"memory": []})()

    orch.run_portfolio_aware_cycle(symbols)

    assert _interleaving_is_per_symbol(orch.calls, symbols), (
        "propose ve finalize sembol bazinda ic ice gecmeli -- toplu "
        f"beklemeye geri donulmus: {orch.calls}"
    )


def test_a_none_proposal_does_not_break_the_per_symbol_order():
    """Veri gelmeyen sembol atlanmalı ama sıra bozulmamalı."""
    symbols = ["AAAUSDT", "BBBUSDT"]
    orch = _Recorder(symbols)
    orch.data_provider = None
    orch.memory = type("M", (), {"memory": []})()

    original_propose = orch.propose

    def propose_with_a_gap(symbol: str):
        if symbol == "AAAUSDT":
            orch.calls.append(("propose", symbol))
            return None
        return original_propose(symbol)

    orch.propose = propose_with_a_gap
    out = orch.run_portfolio_aware_cycle(symbols)

    assert [c for c in orch.calls] == [
        ("propose", "AAAUSDT"), ("propose", "BBBUSDT"), ("finalize", "BBBUSDT"),
    ]
    # Sonuç listesi her sembol için bir kayıt taşımaya devam etmeli.
    assert [r["symbol"] for r in out] == symbols
    assert out[0]["error"] == "no_data"
