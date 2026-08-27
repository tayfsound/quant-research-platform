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
from analytics.market_world_model import compute_block_bootstrap_paths
from services.asset_class_performance_gatherer import _is_production_ai_council
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

DEFAULT_BLOCK_SIZE = 10
DEFAULT_PATH_LENGTH = 50


def gather_market_world_model(
    block_size: int = DEFAULT_BLOCK_SIZE, path_length: int = DEFAULT_PATH_LENGTH,
) -> dict:
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        starting_capital = float(AppSettingsRepository(session).get("starting_capital"))
        closed_trades = DecisionPersistor(session).list_closed_trades(
            limit=2000, exclude_experiment_bucket=PUMP_FADE_EXPERIMENT_BUCKET
        )
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
    return {
        "block_size": block_size,
        "path_length": path_length,
        "n_returns": len(returns),
        "paths": paths,
    }
