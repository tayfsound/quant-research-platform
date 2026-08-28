"""Pump-Fade tarama penceresi (lookback_hours) araştırması — kullanıcı
sorusu (2026-08-28): "%50 barajını ayarladık ama token'ın bunu ne kadar
sürede yapması gerektiği (tarama penceresi) üzerine hiç çalışmadık."

Gerçek, GERÇEK piyasa verisiyle (Binance klines, doğrudan gerçek ağ
isteği — sahte/mock veri YOK) çalışan, salt-okunur bir araştırma
scripti. Hiçbir DB'ye (quantdb/quantdb_test) yazmaz, hiçbir trading
durumunu etkilemez — bu yüzden pytest dışında doğrudan çalıştırılması
GÜVENLİDİR (bkz. AGENT_MEMORY "debug scripts must target test DB" kuralı
— o kural DB/kill-switch mutasyonu riski taşıyan scriptler için, bu
script hiçbirini yapmıyor).

Yöntem: services/pump_fade_strategy.py::find_pump_candidates ile AYNI
tetikleme mantığını (min(low) → current kazanç oranı), gerçek geçmiş
1 saatlik mumlar üzerinde KAYAN bir pencereyle (günlük adımlarla)
tekrar tekrar çalıştırır — her aday `lookback_hours` değeri için. Her
tetiklemeden sonra fiyatın GERÇEKTEN ne yaptığını (ileriye dönük sabit
bir ufuk, varsayılan 72 saat — pump_fade_peak_window_hours ile aynı)
ölçer: pump-fade tezi fiyatın GERİ ÇEKİLMESİni varsayıyor (short/fade),
o yüzden "isabet" = ileriye dönük getirinin NEGATİF olması.

Bu, stop/hedef/kaldıraç dahil TAM bir P&L simülasyonu DEĞİL — sadece
"bu pencere+eşik kombinasyonu ne sıklıkla VE ne kadar güvenilir şekilde
gerçek bir tepe/dönüş yakalıyor" sorusuna gerçek veriyle bir ilk cevap.
"""
from __future__ import annotations

import random
import statistics
from dataclasses import dataclass, field

from market_data.ingestion.data_provider import RoutingProvider
from services.pump_fade_strategy import fetch_usdt_perpetual_symbols

# Binance 1h klines tek istekte en fazla 1000 mum veriyor (~41.6 gün) —
# script bu sınırı aşmıyor, ekstra sayfalama gerekmiyor.
BARS_LIMIT = 1000
FORWARD_HOURS = 72  # pump_fade_peak_window_hours ile aynı ufuk
STEP_HOURS = 24  # günlük adım — üst üste binen neredeyse-aynı tetiklemeleri azaltır
CANDIDATE_WINDOWS = (12, 24, 48, 72, 96, 120, 168)
DEFAULT_SAMPLE_SIZE = 50
DEFAULT_MIN_GAIN_PCT = 0.50  # kullanıcının canlıda ayarladığını söylediği baraj


@dataclass
class WindowResult:
    lookback_hours: int
    trigger_count: int = 0
    forward_returns: list[float] = field(default_factory=list)

    @property
    def fade_hit_rate(self) -> float | None:
        if not self.forward_returns:
            return None
        faded = sum(1 for r in self.forward_returns if r < 0)
        return faded / len(self.forward_returns)

    @property
    def avg_forward_return_pct(self) -> float | None:
        if not self.forward_returns:
            return None
        return statistics.mean(self.forward_returns)

    @property
    def median_forward_return_pct(self) -> float | None:
        if not self.forward_returns:
            return None
        return statistics.median(self.forward_returns)

    @property
    def blowup_rate(self) -> float | None:
        """Fiyat DURMADAN pompalamaya devam etti (ileriye dönük getiri
        >+%15) — bir short/fade pozisyonu için en kötü senaryo, kaç
        tetiklemenin bu şekilde sonuçlandığı."""
        if not self.forward_returns:
            return None
        return sum(1 for r in self.forward_returns if r > 0.15) / len(self.forward_returns)


def _pick_sample_symbols(sample_size: int, seed: int) -> list[str]:
    universe = fetch_usdt_perpetual_symbols()
    if not universe:
        raise RuntimeError("Binance futures sembol listesi çekilemedi — gerçek ağ bağlantısını kontrol edin.")
    rng = random.Random(seed)
    return rng.sample(universe, k=min(sample_size, len(universe)))


def _scan_symbol(bars, min_gain_pct: float) -> dict[int, list[float]]:
    """Tek bir sembolün geçmiş mum dizisi için TÜM aday pencereleri aynı
    anda tarar (aynı `bars` verisi üzerinde, tekrar ağ isteği yok)."""
    per_window: dict[int, list[float]] = {w: [] for w in CANDIDATE_WINDOWS}
    n = len(bars)
    for lookback_hours in CANDIDATE_WINDOWS:
        i = lookback_hours - 1
        while i + FORWARD_HOURS < n:
            window = bars[i - lookback_hours + 1 : i + 1]
            low = min(b.low for b in window)
            current = bars[i].close
            if low > 0 and current > 0:
                gain_pct = (current - low) / low
                if gain_pct >= min_gain_pct:
                    forward_price = bars[i + FORWARD_HOURS].close
                    forward_return_pct = (forward_price - current) / current
                    per_window[lookback_hours].append(forward_return_pct)
            i += STEP_HOURS
    return per_window


def run_study(
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    min_gain_pct: float = DEFAULT_MIN_GAIN_PCT,
    seed: int = 7,
) -> list[WindowResult]:
    symbols = _pick_sample_symbols(sample_size, seed)
    provider = RoutingProvider()
    results = {w: WindowResult(lookback_hours=w) for w in CANDIDATE_WINDOWS}

    fetched = 0
    for symbol in symbols:
        try:
            bars = provider.get_ohlcv(symbol, "1h", limit=BARS_LIMIT)
        except Exception:
            continue
        if len(bars) < max(CANDIDATE_WINDOWS) + FORWARD_HOURS:
            continue
        fetched += 1
        per_window = _scan_symbol(bars, min_gain_pct)
        for w, returns in per_window.items():
            results[w].trigger_count += len(returns)
            results[w].forward_returns.extend(returns)

    print(f"\n{fetched}/{len(symbols)} sembol için yeterli geçmiş veri bulundu, min_gain_pct=%{min_gain_pct * 100:.0f}\n")
    return list(results.values())


def print_report(results: list[WindowResult]) -> None:
    header = f"{'Pencere (saat)':>14} | {'Tetikleme':>9} | {'Fade isabet':>11} | {'Ort. ileri getiri':>17} | {'Medyan':>8} | {'Patlama (>+%15)':>15}"
    print(header)
    print("-" * len(header))
    for r in results:
        hit = f"%{r.fade_hit_rate * 100:.1f}" if r.fade_hit_rate is not None else "—"
        avg = f"%{r.avg_forward_return_pct * 100:+.2f}" if r.avg_forward_return_pct is not None else "—"
        med = f"%{r.median_forward_return_pct * 100:+.2f}" if r.median_forward_return_pct is not None else "—"
        blow = f"%{r.blowup_rate * 100:.1f}" if r.blowup_rate is not None else "—"
        print(f"{r.lookback_hours:>14} | {r.trigger_count:>9} | {hit:>11} | {avg:>17} | {med:>8} | {blow:>15}")


if __name__ == "__main__":
    results = run_study()
    print_report(results)
