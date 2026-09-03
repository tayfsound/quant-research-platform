"""Market World Model'ın girdisini GERÇEK kapanmış işlemlerden toplayan
tek kaynak — Cognitive Core 5.0-6.0 (Faz 901-940).
analytics/market_world_model.py::compute_block_bootstrap_paths() saf
(pure) kalıyor — gerçek veriye dokunan kod burada.

services/self_model_gatherer.py ile AYNI gerçek-getiri kaynağı (kronolojik
kapanmış işlemler, pump_fade_v1 hariç — mekanik strateji, council'in
gerçek getiri dağılımıyla ilgisi yok) — veri çekme icat/tekrar edilmiyor.

Faz 366-devam — kritik bulgu (harici bir GPT incelemesi + kullanıcı
onayı): önceden buraya beslenen "getiri" ham VARLIK fiyat getirisiydi
(sign * (exit-entry)/entry) — gerçek kaldıraçlı pozisyon PnL%'i DEĞİL,
compute_block_bootstrap_paths'in compounding formülü (1+r>0 varsayımı)
bazı SHORT'larda kırılıp -%1748 gibi anlamsız değerler üretiyordu.

İlk düzeltme denemesi (pnl / margin, margin=entry*quantity/leverage)
tek başına YETERSİZ çıktı — iki AYRI ek sorunu ortaya çıkardı:
1. Bu fonksiyon pump_fade_v1'i hariç tutuyordu ama basis_arb_v1'i HİÇ
   hariç tutmuyordu. basis_arb_v1 (Faz 364'te mimariden kaldırıldı)
   backlog madde 30'da belgelenmiş gerçek likidasyon-gecikmesi hataları
   içeriyor (gerçek örnek: BTRUSDT SHORT, margin=$100 ama pnl=-$1864 —
   likidasyon fiyatını geçtikten SONRA kapanmış, mekanik stratejinin
   kendi hatası). confidence_calibration.py/kelly_sizing.py (Faz 363,
   backlog #36) AYNI izolasyonu zaten yapıyordu, bu gatherer'ın gözden
   kaçtığı ortaya çıktı.
2. Bunu da düzeltince BİLE kümülatif değerler hâlâ anlamsızdı (ortalama
   %744 trilyon). Kök neden: pnl/margin, HER işlemin kendi (kaldıraçlı)
   marjinine göre getirisini ölçüyor — 50 işlemi ardışık compound etmek,
   HER işlemde büyüyen bakiyenin TAMAMININ yeniden 5-10x kaldıraçla
   yatırıldığını varsayıyor, ki bu sistemin GERÇEK boyutlandırması hiç
   böyle çalışmıyor (her işlem toplam sermayenin küçük bir dilimini
   riske atıyor — capital_per_trade, bkz. app_settings). Doğru payda
   `starting_capital` (backtest/red_team.py'nin AYNI ilkesi: "gerçek bir
   equity eğrisi değil, sabit bir taban sermayeye göre kümülatif kâr/
   zarar") — her işlemin pnl'i TOPLAM sermayeye göre ölçülünce (gerçek
   veriyle doğrulandı: tipik işlem ±%0.01-0.05 arası, asla patlamıyor),
   50 işlemi ardışık compound etmek matematiksel olarak anlamlı.

Faz 367-devam — kullanıcı bulgusu (2026-08-27, bkz. asset_class_
performance_gatherer.py'nin AYNI notu): multi_timeframe_cascade_v1 (A/B
deneyi) de basis_arb_v1 ile AYNI şekilde hariç tutuluyor — bu modülün
amacı "gerçek AI konseyi getiri dağılımı"nı simüle etmek, deneysel
varyansı değil (basis_arb_v1 zaten aynı gerekçeyle hariçti)."""
from analytics.evaluation_cohort import describe_evaluation_window
from analytics.market_world_model import compute_block_bootstrap_paths, compute_block_size_sensitivity
from analytics.measurement_stability import compute_stability
from services.asset_class_performance_gatherer import _is_production_ai_council
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

DEFAULT_BLOCK_SIZE = 10
DEFAULT_PATH_LENGTH = 50
STABILITY_LOOKBACK_SNAPSHOTS = 12
_PATH_STABILITY_FIELDS = ("mean_cumulative_return", "p5_cumulative_return", "worst_max_drawdown")


def _attach_paths_stability(paths: dict | None, past_snapshots: list[dict]) -> None:
    """Faz 407 — kullanıcı isteği: "ölçtüğümüz her veri için zaman
    içindeki stabilitesini de ölçelim." Bootstrap simülasyonunun (sabit
    random_seed=42 ile deterministik) ana özet skalerlerinin haftadan
    haftaya ne kadar tutarlı olduğunu ekliyor — SADECE gözlem."""
    if paths is None:
        return
    past_by_field: dict[str, list[float]] = {}
    for snap in past_snapshots:
        snap_paths = (snap.get("result") or {}).get("paths") or {}
        for field in _PATH_STABILITY_FIELDS:
            if field in snap_paths:
                past_by_field.setdefault(field, []).append(snap_paths[field])

    paths["stability"] = {
        field: compute_stability([*past_by_field.get(field, []), paths.get(field)])
        for field in _PATH_STABILITY_FIELDS
    }


def gather_market_world_model(
    block_size: int = DEFAULT_BLOCK_SIZE, path_length: int = DEFAULT_PATH_LENGTH,
) -> dict:
    """Faz 369-devam — GPT dış rapor önerisi: "block=10 seçimi sonucu
    ciddi etkileyebilir, block=5/10/20/30 ile ayrı ayrı simülasyon yapıp
    karşılaştırmak isterim." AYNI (zaten çekilmiş) returns dizisi, ek bir
    DB sorgusu OLMADAN, block_size_sensitivity taramasına da besleniyor —
    canlı sayfanın "block=10'daki tek nokta ne kadar güvenilir" sorusuna
    her istekte taze cevap vermesi için."""
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.repositories.decision_persistor import DecisionPersistor
    from database.repositories.market_world_model_report_repository import (
        MarketWorldModelReportRepository,
    )
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        starting_capital = float(AppSettingsRepository(session).get("starting_capital"))
        closed_trades = DecisionPersistor(session).list_closed_trades(
            limit=2000, exclude_experiment_bucket=PUMP_FADE_EXPERIMENT_BUCKET
        )
        past_snapshots = MarketWorldModelReportRepository(session).get_recent(STABILITY_LOOKBACK_SNAPSHOTS)
    closed_trades = [t for t in closed_trades if _is_production_ai_council(t.get("experiment_bucket"))]

    # Kronolojik sıraya çevir — list_closed_trades opened_at DESC döner,
    # Moving Block Bootstrap'in gerçek ardışık bağımlılık yapısını
    # koruyabilmesi için ESKİDEN YENİYE sıralanması gerekiyor.
    ordered = sorted(closed_trades, key=lambda t: t.get("closed_at") or t.get("opened_at"))

    returns = []
    if starting_capital > 0:
        for t in ordered:
            pnl = t.get("pnl")
            if pnl is not None:
                returns.append(pnl / starting_capital)

    paths = compute_block_bootstrap_paths(returns, block_size=block_size, path_length=path_length)
    _attach_paths_stability(paths, past_snapshots)
    block_size_sensitivity = compute_block_size_sensitivity(returns, path_length=path_length)
    # Faz 400 — kritik bulgu: bu modülün TEK "n_*" alanı (n_returns)
    # returns listesinin (starting_capital>0 şartından SONRA) uzunluğunu
    # anlatıyordu, gerçek kapanmış-işlem N'ini (closed_trades, filtreler
    # UYGULANMIŞ hâliyle) DEĞİL — canonical evaluation cohort görünürlüğü
    # için ayrı, doğru bir alan.
    evaluation_window = describe_evaluation_window(
        closed_trades, limit=2000,
        exclude_experiment_buckets=[PUMP_FADE_EXPERIMENT_BUCKET],
        production_ai_council_filtered=True,
    )
    return {
        "block_size": block_size,
        "path_length": path_length,
        "n_returns": len(returns),
        "paths": paths,
        "block_size_sensitivity": block_size_sensitivity,
        "evaluation_window": evaluation_window,
    }
