"""Adversarial Red-Team modu — kasıtlı kötü senaryo üretimi.

Faz 268-sonrası: backtest/real_historical_backtest.py GERÇEK Binance
geçmişiyle GERÇEK council'i besliyor — ama "iyi/normal" piyasada ne
olduğunu gösteriyor, "en kötü ihtimalde savunmalar gerçekten tutuyor mu"
sorusunu cevaplamıyor. Bu modül SENTETİK, kasıtlı olarak kötü fiyat
serileri (whipsaw, flash crash, korele çoklu-varlık çöküşü) üretip
bunları AYNI GERÇEK altyapı (CognitiveEngine — 10 ajanlı council +
RiskEngine + DrawdownSizingStage — ve real_historical_backtest.py'nin
zaten test edilmiş context/exit simülasyonu) üzerinden koşturuyor. Amaç
"council ne düşünürdü" değil: "kill switch/drawdown sizing/max drawdown
limiti gerçekten sermayeyi koruyor mu, yoksa sadece sakin piyasada mı
çalışıyorlar" sorusunu gerçek koda karşı test etmek.

Kasıtlı olarak _build_backtest_context/_simulate_real_exit'i (real_
historical_backtest.py) TEKRAR YAZMIYOR, doğrudan import edip üstüne
sadece kill switch/drawdown-sizing için gereken SIRALI durumu (ctx.risk.
consecutive_losses/ai_enabled/current_drawdown, bir SONRAKİ bar'a
taşınan) ekliyor — "iki beyin" riskini (aynı context/exit mantığının
ikinci, sapabilecek bir kopyası) önlemek için.

Basitleştirme (dürüstçe belirtilmeli): capital_per_trade SABİT kalıyor,
önceki işlemlerin kâr/zararına göre YENİDEN ölçeklenmiyor (gerçek
compounding yok) — DrawdownSizingStage'in final_size'ı küçültme etkisini
ve kill switch'in tamamen durdurma etkisini ölçmek için yeterli, ama
final_pnl_pct "gerçek bir equity eğrisi" değil, "sabit bir taban sermayeye
göre kümülatif kâr/zarar" olarak okunmalı.

GÜVENLİK NOTU — kritik, dikkatli okunmalı: RiskEngine._trip_kill_switch()
kill switch eşiği aşıldığında app_settings.ai_enabled=false'ı GERÇEKTEN
DB'ye yazıyor (bkz. engines/risk_engine.py) — bu yazma persist=False ile
ATLANMIYOR, GuardrailStage HER engine.run() çağrısında koşuluyor. Bu
modülün senaryoları kasıtlı olarak kill switch'i TETİKLEMEYE çalışıyor,
bu yüzden run_red_team_scenario() SADECE pytest altında (kök conftest.py
DATABASE_URL_SYNC'i quantdb_test'e yönlendiriyor, uygulama kodu import
edilmeden ÖNCE) çağrılmalı — DATABASE_URL_SYNC unset/live iken ad-hoc bir
script'ten çağırmak GERÇEK canlı ai_enabled'ı kapatabilir.

Diğer güvenlik notu — bkz. tests/test_real_historical_backtest.py'nin
kendi notu: ctx.market.features doldurulunca MemoryStage gerçek embedding
modelini (sentence-transformers) tetikliyor — standart `transformers.*`
mock deseniyle ÇALIŞMIYOR (MagicMock, torch .to() ile patlıyor). Bu
modülün testleri o yüzden transformers'ı mock'LAMAMALI, gerçek (yerel
önbellekli) modelin yüklenmesine izin vermeli."""
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from backtest.real_historical_backtest import _build_backtest_context, _simulate_real_exit
from contracts.contexts.risk import RiskLimitEntry
from market_data.features.signal_engine import compute_daily_atr_pct
from market_data.ingestion.ohlcv import OHLCV
from services.cognitive_engine import CognitiveEngine
from simulator.fee_engine import FeeEngine


def whipsaw_chop(base_price: float = 100.0, n_bars: int = 150, amplitude_pct: float = 0.05, period_bars: int = 4) -> list[OHLCV]:
    """Sağlıksız, hızlı yön değişimleri — bir trend-takip stratejisinin
    art arda yanlış tarafta kalmasına neden olan klasik "whipsaw" deseni.
    Faz 268-sonrası'nın gerçek olayıyla (2026-08-12, 50 ardışık gerçek
    LONG kaybı — gecikmeli long_term_trend_regime aktif bir tersine
    dönüşü zamanında okuyamamıştı) AYNI mekanizma, kasıtlı olarak sentetik
    biçimde üretiliyor."""
    now = datetime.now(UTC)
    bars: list[OHLCV] = []
    price = base_price
    for i in range(n_bars):
        direction = 1.0 if (i // period_bars) % 2 == 0 else -1.0
        price = price * (1 + direction * amplitude_pct / period_bars)
        bars.append(OHLCV(
            timestamp=now + timedelta(minutes=i), open=price,
            high=price * 1.002, low=price * 0.998, close=price, volume=100.0,
        ))
    return bars


def flash_crash_and_recover(
    base_price: float = 100.0, n_bars: int = 100, crash_at_bar: int = 40,
    crash_depth_pct: float = 0.35, recovery_bars: int = 40,
) -> list[OHLCV]:
    """Ani, sert bir çöküş (birkaç bar içinde) ardından düz değil, dalgalı/
    kararsız bir kısmi toparlanma — "dip alındı" sanılıp hemen tekrar dönen
    klasik bull-trap deseni, art arda yanlış giriş riski."""
    now = datetime.now(UTC)
    bars: list[OHLCV] = []
    price = base_price
    crash_floor = base_price * (1 - crash_depth_pct)
    for i in range(n_bars):
        if i < crash_at_bar:
            price = base_price
        elif i < crash_at_bar + 3:
            frac = (i - crash_at_bar + 1) / 3
            price = base_price - (base_price - crash_floor) * frac
        elif i < crash_at_bar + 3 + recovery_bars:
            progress = (i - crash_at_bar - 3) / recovery_bars
            wobble = math.sin(progress * math.pi * 4) * crash_depth_pct * 0.15
            price = crash_floor + (base_price * 0.6 - crash_floor) * progress + crash_floor * wobble
        bars.append(OHLCV(
            timestamp=now + timedelta(minutes=i), open=price,
            high=price * 1.003, low=price * 0.997, close=price, volume=100.0,
        ))
    return bars


def correlated_multi_asset_crash(
    symbols: list[str], base_prices: dict[str, float] | None = None,
    n_bars: int = 100, crash_at_bar: int = 40, crash_depth_pct: float = 0.30,
) -> dict[str, list[OHLCV]]:
    """Birden fazla sembol AYNI anda, neredeyse özdeş bir çöküş yaşıyor —
    "farklı sembollere dağıtınca risk azalır" varsayımının çöktüğü, piyasa
    genelinde korelasyonun 1'e yaklaştığı stres anı. Küçük, deterministik
    sembol-bazlı bir gecikme/derinlik farkı dışında hepsi aynı çöküş
    şeklini paylaşıyor. NOT: her sembol run_red_team_scenario'ya AYRI
    çağrılır (CognitiveEngine.run() tek-sembollü) — bu senaryo cross-
    symbol korelasyon indirimini DEĞİL (o mekanizma services/orchestrator.
    py::_apply_portfolio_fusion'da, farklı bir kod yolu), portföy
    genelinde eş-zamanlı sermaye kaybı riskini test eder."""
    base_prices = base_prices or {s: 100.0 for s in symbols}
    result: dict[str, list[OHLCV]] = {}
    for idx, symbol in enumerate(symbols):
        offset_bars = idx
        depth = crash_depth_pct * (1.0 - 0.05 * idx)
        result[symbol] = flash_crash_and_recover(
            base_price=base_prices.get(symbol, 100.0), n_bars=n_bars,
            crash_at_bar=crash_at_bar + offset_bars, crash_depth_pct=depth,
            recovery_bars=n_bars - crash_at_bar - offset_bars - 10,
        )
    return result


@dataclass
class RedTeamResult:
    scenario: str
    n_bars: int
    trades_taken: int
    kill_switch_tripped: bool
    kill_switch_tripped_at_bar: int | None
    max_consecutive_losses: int
    max_drawdown_pct: float
    final_pnl_pct: float


def run_red_team_scenario(
    bars: list[OHLCV],
    *,
    scenario_name: str = "custom",
    lookback: int = 60,
    max_forward_bars: int = 15,
    kill_switch_consecutive_losses: int = 10,
    max_drawdown_limit_pct: float = 0.5,
    capital_per_trade: float = 1000.0,
    engine: CognitiveEngine | None = None,
) -> RedTeamResult:
    """Sentetik bir bar dizisini GERÇEK CognitiveEngine.run() üzerinden
    (gerçek council + RiskEngine + DrawdownSizingStage) bar-bar koşturur.
    Context/stop-target-exit simülasyonu real_historical_backtest.py'nin
    ZATEN test edilmiş fonksiyonlarıyla (_build_backtest_context,
    _simulate_real_exit) kuruluyor — burada SADECE kill switch/drawdown
    sizing'in ihtiyaç duyduğu SIRALI durum (consecutive_losses/ai_enabled/
    current_drawdown) ekleniyor, production'daki services/risk_state.py'nin
    yaptığının simüle edilmiş karşılığı: bar t'nin sonucu ÖNCE (kısa bir
    ufuk, max_forward_bars, içinde gerçek stop/target ile) gerçekleşiyor,
    SONRA bar t+1'in ctx.risk'ine besleniyor.

    NOT: bkz. bu dosyanın modül docstring'indeki iki güvenlik notu."""
    engine = engine or CognitiveEngine()
    n_bars = len(bars)

    consecutive_losses = 0
    max_consecutive_losses_seen = 0
    ai_enabled = True
    kill_switch_tripped = False
    kill_switch_tripped_at_bar: int | None = None
    cumulative_pnl_usd = 0.0
    peak_pnl_usd = 0.0
    max_drawdown_seen = 0.0
    trades_taken = 0
    fee_engine = FeeEngine()

    for t in range(lookback, n_bars - 1):
        window = bars[max(0, t - lookback): t + 1]
        current_drawdown = (peak_pnl_usd - cumulative_pnl_usd) / capital_per_trade
        max_drawdown_seen = max(max_drawdown_seen, current_drawdown)

        daily_atr_pct = compute_daily_atr_pct(window, period=14)
        ctx = _build_backtest_context("REDTEAM", "15m", window, capital_per_trade, daily_atr_pct=daily_atr_pct)
        ctx.risk.limits["max_drawdown"] = RiskLimitEntry(value=max_drawdown_limit_pct)
        ctx.risk.current_drawdown = current_drawdown
        ctx.risk.ai_enabled = ai_enabled
        ctx.risk.consecutive_losses = consecutive_losses
        ctx.risk.kill_switch_consecutive_losses = kill_switch_consecutive_losses

        result_ctx = engine.run(ctx, persist=False)

        if result_ctx.risk.evaluation.verdict == "rejected":
            if not result_ctx.risk.ai_enabled and not kill_switch_tripped:
                kill_switch_tripped = True
                kill_switch_tripped_at_bar = t
            ai_enabled = result_ctx.risk.ai_enabled
            continue

        direction = result_ctx.decision.proposed_direction or "WAIT"
        size = result_ctx.decision.final_size or 0.0
        if direction not in ("LONG", "SHORT") or size <= 0:
            continue

        risk_mag = result_ctx.decision.stop_loss
        reward_mag = result_ctx.decision.take_profit
        if not risk_mag or not reward_mag:
            continue

        entry_price = bars[t].close
        if direction == "LONG":
            stop_price = entry_price - risk_mag
            target_price = entry_price + reward_mag
        else:
            stop_price = entry_price + risk_mag
            target_price = entry_price - reward_mag

        exit_price, exit_reason, _exit_idx = _simulate_real_exit(
            bars, t, direction, stop_price, target_price, max_forward_bars,
        )
        if exit_price is None:
            continue  # ufuk içinde kapanmadı — uydurma bir sonuç İCAT EDİLMEZ (fail-closed)

        if direction == "LONG":
            gross_pnl_pct = (exit_price - entry_price) / entry_price
        else:
            gross_pnl_pct = (entry_price - exit_price) / entry_price

        exit_is_maker = exit_reason == "take_profit"
        entry_fee_pct = fee_engine.config.taker_rate
        exit_fee_pct = fee_engine.config.maker_rate if exit_is_maker else fee_engine.config.taker_rate
        net_pnl_pct = gross_pnl_pct - entry_fee_pct - exit_fee_pct
        net_pnl_usd = net_pnl_pct * size * entry_price

        trades_taken += 1
        cumulative_pnl_usd += net_pnl_usd
        peak_pnl_usd = max(peak_pnl_usd, cumulative_pnl_usd)

        consecutive_losses = consecutive_losses + 1 if net_pnl_usd < 0 else 0
        max_consecutive_losses_seen = max(max_consecutive_losses_seen, consecutive_losses)

    final_drawdown = (peak_pnl_usd - cumulative_pnl_usd) / capital_per_trade
    max_drawdown_seen = max(max_drawdown_seen, final_drawdown)

    return RedTeamResult(
        scenario=scenario_name,
        n_bars=n_bars,
        trades_taken=trades_taken,
        kill_switch_tripped=kill_switch_tripped,
        kill_switch_tripped_at_bar=kill_switch_tripped_at_bar,
        max_consecutive_losses=max_consecutive_losses_seen,
        max_drawdown_pct=max_drawdown_seen,
        final_pnl_pct=cumulative_pnl_usd / capital_per_trade,
    )
