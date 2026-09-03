"""Faz 187: gerçek açık pozisyon / kapanmış işlem (paper trading) API.

Binance tarzı "my trades" görünümü için gerekli tek gerçek kaynak — decisions
tablosundaki status='open'/'closed' satırları, services/position_closer.py
tarafından gerçek zaman geçtikten sonra gerçek fiyatla kapatılıyor."""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from analytics.evaluation_cohort import describe_evaluation_window
from contracts.auth import Role
from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from market_data.ingestion.data_provider import RoutingProvider
from services.auth_service import AuthContext, get_current_user, require_role
from services.position_closer import PositionCloser, fetch_current_prices_by_symbol

router = APIRouter(tags=["positions"])


def _extract_pairs_trade(row: dict) -> str | None:
    """Faz 268ad — kullanıcı: "sistem hedge işlem hiç denemiyor galiba."
    Gerçek: services/pairs_trader.py düzenli (5 dakikada bir, celery beat)
    çalışıyor ve GERÇEK iki-bacaklı (LONG+SHORT) hedge pozisyonları açıyor
    (doğrulandı: son 5 günde 20 bacak, BTCUSDT/ETHUSDT + GC=F/SI=F). Sorun
    kullanıcının algıladığı gibi "hiç çalışmıyor" değil — hiçbir yerde
    görünür değil, normal yönlü işlemlerden ayırt edilemiyor. `decisions`
    tablosunda ayrı bir sütun yok ama pair etiketi zaten agent_contributions
    JSONB'sindeki market_snapshot.raw_snapshot.pairs_trade içinde duruyor
    (bkz. PairsTrader._open_leg) — burada geri okunuyor."""
    for item in row.get("agent_contributions") or []:
        if isinstance(item, dict) and item.get("type") == "market_snapshot":
            raw_snapshot = (item.get("data") or {}).get("raw_snapshot") or {}
            return raw_snapshot.get("pairs_trade")
    return None


# Faz 268f — kullanıcı isteği: "kısa/orta/uzun/swing/scalp gibi işlem
# tiplerinden hangileri başarılı olmuş, dashboard'a otomatik yansısın."
# Transactions.tsx::tradeTypeBadge() ile AYNI sınıflandırma — tek gerçek
# kaynak, biri backend (agregasyon) biri frontend (satır rozeti) için
# burada tekrarlanıyor. Eşik (%4.5) gerçek kapanmış işlem dağılımından
# kalibre edildi (Faz 268ad).
#
# Faz 317 — kullanıcı kararı: "gün içi" (%4.5-%9) kovası kaldırıldı.
# Gerçek veriyle doğrulandı: 419 "gün içi" işleminin TAMAMI 2026-08-06/14
# arası, %70'i manual_full (gerçek AI kararı değil), ortalama pozisyon
# büyüklüğü $27.73 — eski/kirli test verisi, o tarihten bu yana tek bir
# yeni "gün içi" işlem yok. Kullanıcı: "gün içi işlem diye bir şey
# kalmasın... zaten işlem almıyormuş ölü yatırım." Geçmiş kirli satırlar
# migration faz317 ile excluded_from_stats=true işaretlendi (silinmedi);
# kategori scalp/swing ikili ayrımına birleştirildi.
#
# Faz 323 — kullanıcı bulgusu: "orta_vadeli" (timeframe IN ('4h','1d'))
# kategorisi de kaldırıldı. Kök neden: `timeframe` (decisions.timeframe,
# candle_timeframe ayarının karar anındaki değeri) risk profiliyle değil
# HANGİ MEKANİZMANIN kararı verdiğiyle ilgili — kırılgan bir vekildi.
# İki gerçek kaynağı vardı: (1) ~1016 işlem gerçek bir A/B deneyinden
# (multi_timeframe_cascade_v1, services/orchestrator.py::
# run_portfolio_aware_cycle) — "control" kolu bile normal propose() ile
# AYNI mekanizma, sadece deney etiketi taşıyordu; (2) ~108 işlem
# candle_timeframe'in 2026-08-14→08-20 arası yanlışlıkla 4h/1d'de
# kalmasından (Faz316'da bulunan/düzeltilen AYNI ayar sorunu) — scalp/
# swing'i 6 gün boyunca hiç yeni kayıt almadan dondurmuştu. Her iki
# kaynak da gerçek stop mesafesine göre incelendiğinde doğal bir scalp/
# swing dağılımı gösteriyordu (control: ort. %1.13 dar / %9.80 geniş).
# Deney karşılaştırması zaten experiment_bucket üzerinden ayrı yapılıyor
# (services/ab_testing.py) — dashboard'da risk-profili sınıflandırmasıyla
# ÇAKIŞAN, candle_timeframe gibi ilgisiz ayarlara karşı kırılgan üçüncü
# bir kategoriye gerek yok. Artık HER işlem (deneyler dahil) SADECE gerçek
# stop mesafesine göre scalp/swing'e ayrılıyor.
_SCALP_MAX_STOP_PCT = 4.5


def _classify_trade_type(row: dict) -> str | None:
    # Faz 268-sonrası — kullanıcı bulgusu: "Pump-Fade ile açtığı işlem var
    # mı Transactions'ta göremedim." Kök neden: pump_fade_strategy.py bu
    # işlemleri experiment_bucket="pump_fade_v1" ile etiketliyordu ama bu
    # sütun ne burada ne de _serialize()'da hiç okunmuyordu — pump-fade
    # işlemleri sessizce stop-mesafesi sezgiselliğine (scalp/swing)
    # düşüp normal AI işlemlerinden ayırt edilemez oluyordu. Diğer
    # dallardan ÖNCE kontrol ediliyor çünkü mekanik strateji, stop mesafesi
    # tesadüfen scalp/swing aralığına denk gelse bile kendi kimliğini
    # korumalı.
    if row.get("experiment_bucket") == "pump_fade_v1":
        return "pump_fade"
    # Faz 344 — Cross-Asset Arbitrage Engine, pump_fade ile AYNI desen:
    # kendi experiment_bucket'ı, diğer dallardan ÖNCE kontrol ediliyor ki
    # stop mesafesi sezgiselliğine (bu strateji zaten hiç stop set
    # etmiyor) sessizce düşüp kimliğini kaybetmesin.
    if row.get("experiment_bucket") == "basis_arb_v1":
        return "basis_arb"
    if _extract_pairs_trade(row):
        return "hedge"
    entry_price = row.get("entry_price")
    stop_loss_price = row.get("stop_loss_price")
    if entry_price and stop_loss_price and entry_price != 0:
        pct = abs(entry_price - stop_loss_price) / entry_price * 100
        if pct < _SCALP_MAX_STOP_PCT:
            return "scalp"
        return "swing"
    return None


def _serialize(row: dict, current_price: float | None = None, net_unrealized_pnl: float | None = None) -> dict:
    outcome = row.get("outcome") or {}
    return {
        "id": str(row["id"]),
        "symbol": row["symbol"],
        "direction": row["direction"],
        "entry_price": row.get("entry_price"),
        "exit_price": row.get("exit_price"),
        "quantity": row.get("quantity"),
        "confidence": row.get("confidence"),
        "status": row.get("status"),
        "pnl": row.get("pnl"),
        "stop_loss_price": row.get("stop_loss_price"),
        "take_profit_price": row.get("take_profit_price"),
        "leverage": row.get("leverage"),
        "liquidation_price": row.get("liquidation_price"),
        "timeframe": row.get("timeframe"),
        "pairs_trade": _extract_pairs_trade(row),
        "trade_type": _classify_trade_type(row),
        # Faz 315 — Execution Layer, Faz 1. Dashboard'un "testnet" rozeti
        # için: bu pozisyon simülasyon mu yoksa gerçek Binance Futures
        # Testnet emirleriyle mi açıldı/yönetiliyor.
        "execution_mode": row.get("execution_mode"),
        "exit_reason": outcome.get("exit_reason"),
        "realized_pnl": outcome.get("realized_pnl"),
        # Faz 268p — kullanıcı isteği: "pozisyon o an karda mı zararda mı
        # göremiyorum." current_price/net_unrealized_pnl SADECE açık
        # pozisyonlar için (GET /positions'tan) dolduruluyor — komisyon
        # düşülmüş, "şimdi kapatsam cebe ne geçer" rakamı (services/
        # position_closer.py::estimate_net_pnl_if_closed_now ile AYNI
        # formül, toplu-kapatma kararıyla asla çelişmesin diye).
        "current_price": current_price,
        "net_unrealized_pnl": net_unrealized_pnl,
        "opened_at": row["opened_at"].isoformat() if row.get("opened_at") else None,
        "closed_at": row["closed_at"].isoformat() if row.get("closed_at") else None,
    }


_DISPLAY_PRICE_CACHE: dict[str, tuple[float, float]] = {}
_DISPLAY_PRICE_CACHE_TTL_SECONDS = 8.0


def _fetch_current_prices(symbols: set[str]) -> dict[str, float]:
    """Faz 268p/268w: her benzersiz sembol için TEK bir fiyat çekiyor
    (100'lerce pozisyon aynı ~10-15 watchlist sembolünü paylaşıyor) —
    pozisyon başına değil, sembol başına bir istek.

    Faz 268w — kritik bulgu: kullanıcı "Transactions çok yavaş açılıyor"
    dedi. Gerçek ölçüm: GET /positions 1.7 saniye sürüyordu — 15 benzersiz
    sembolün HER BİRİ için SIRALI (ardışık) bir gerçek Binance/Yahoo
    isteği atılıyordu, biri bitmeden diğeri başlamıyordu. get_ohlcv senkron
    (bloklayan) bir çağrı olduğu için ThreadPoolExecutor ile GERÇEKTEN
    paralel çekiliyor artık — 15 sıralı istek yerine 15 istek aynı anda,
    toplam süre en yavaş TEK isteğe iniyor (~15 kat değil, ~1 kat gecikme).
    Bir sembol çekilemezse (fail-closed) sadece o sembol sözlükte hiç yer
    almaz, diğerleri etkilenmez.

    Faz 347 — kullanıcı bulgusu ("sistem genel olarak hantal"): gerçek
    ölçüm — Binance hız sınırlayıcısı (exchange_gateway/binance/
    rate_limit.py, saniyede 15 istek, TÜM süreçler arasında Redis'te
    PAYLAŞILIYOR) yüzünden 66 benzersiz sembol için bu çağrı ~9 saniye
    sürüyor — VE bu bütçe canlı trading döngüsüyle (run_trading_cycle_
    task, close_due_positions_task vb.) AYNI anda paylaşılıyor, dashboard
    her açıldığında/15sn'de bir yenilendiğinde canlı döngüyle çakışıyor.
    Kısa süreli (8sn) bir SÜREÇ-İÇİ önbellek — SADECE bu GÖRÜNTÜLEME
    fonksiyonuna özel, services/position_closer.py::fetch_current_
    prices_by_symbol'e (stop/hedef/likidasyon kontrolü — Faz 334'ün
    stop_loss overshoot düzeltmesinin tam ilgilendiği yer) KASITLI
    olarak BULAŞMIYOR — o fonksiyon her zaman taze fiyat ister, gecikme
    orada güvenlik riski olurdu. Burada SADECE kullanıcıya gösterilen
    bir sayı, 8sn'lik bayatlık kabul edilebilir bir tercih."""
    import time

    now = time.monotonic()
    cached_hits: dict[str, float] = {}
    stale_or_missing: set[str] = set()
    for symbol in symbols:
        cached = _DISPLAY_PRICE_CACHE.get(symbol)
        if cached is not None and (now - cached[0]) < _DISPLAY_PRICE_CACHE_TTL_SECONDS:
            cached_hits[symbol] = cached[1]
        else:
            stale_or_missing.add(symbol)

    fresh = fetch_current_prices_by_symbol(stale_or_missing) if stale_or_missing else {}
    for symbol, price in fresh.items():
        _DISPLAY_PRICE_CACHE[symbol] = (now, price)

    return {**cached_hits, **fresh}


@router.get("/positions")
def list_open_positions(
    limit: int = 100, offset: int = 0, user: AuthContext = Depends(get_current_user)
):
    with SessionFactory.get_session() as session:
        persistor = DecisionPersistor(session)
        rows = persistor.list_open_positions(limit=limit, offset=offset)
        summary = persistor.open_positions_summary()
        # Kullanıcı isteği: "açık pozisyonların yüzde kaçı karda yüzde kaçı
        # zararda." TÜM açık pozisyonlar üzerinden olmalı (sadece bu sayfa
        # değil) — ama gerçek ölçüm: 747 pozisyon/134 sembolde tam bir
        # tarama ~30 saniye sürüyor (fiyat çekme + finansman maliyeti).
        # İstek anında hesaplamak Faz 268w'nin düzelttiği "Transactions
        # çok yavaş açılıyor" sorununu geri getirirdi — bunun yerine
        # refresh_open_position_pnl_summary_task dakikada bir arka planda
        # hesaplayıp app_settings'e yazıyor, burası sadece okuyor (anlık).
        settings_repo = AppSettingsRepository(session)
        summary["profit_count"] = int(settings_repo.get("open_positions_profit_count") or 0)
        summary["loss_count"] = int(settings_repo.get("open_positions_loss_count") or 0)

    prices = _fetch_current_prices({r["symbol"] for r in rows})
    closer = PositionCloser(RoutingProvider())

    positions = []
    for r in rows:
        price = prices.get(r["symbol"])
        net_pnl = closer.estimate_net_pnl_if_closed_now(r, price) if price is not None else None
        positions.append(_serialize(r, current_price=price, net_unrealized_pnl=net_pnl))

    return {
        "positions": positions,
        "summary": summary,
    }


@router.get("/positions/breakdown-by-type")
def positions_breakdown_by_type(
    exclude_experiment_bucket: str | None = None,
    user: AuthContext = Depends(get_current_user),
):
    """Faz 268-sonrası — kullanıcı isteği: "scalp, gün içi, orta vade vs.
    farklı işlem türlerinin ne kadarı short ne kadarı long pozisyonmuş."
    _classify_trade_type() ile AYNI sınıflandırma, ama TÜM açık
    pozisyonları (2000+) tek tek serialize etmek yerine tek bir SQL
    agregasyonu — bkz. decision_persistor.py::open_position_breakdown_
    by_trade_type()."""
    with SessionFactory.get_session() as session:
        rows = DecisionPersistor(session).open_position_breakdown_by_trade_type(
            exclude_experiment_bucket=exclude_experiment_bucket
        )
    return {"breakdown": rows}


@router.get("/trades/breakdown-by-type")
def trades_breakdown_by_type(
    exclude_experiment_bucket: str | None = None,
    user: AuthContext = Depends(get_current_user),
):
    """Kullanıcı isteği: "kapanmış işlemlerin olduğu kısıma ratioları
    eklememişsin oradaki bilgiye de ihtiyacım var" — yukarıdaki açık
    pozisyon kırılımının kapanmış işlemler karşılığı, AYNI SQL
    agregasyonu (bkz. decision_persistor.py::closed_trade_breakdown_
    by_trade_type())."""
    with SessionFactory.get_session() as session:
        rows = DecisionPersistor(session).closed_trade_breakdown_by_trade_type(
            exclude_experiment_bucket=exclude_experiment_bucket
        )
    return {"breakdown": rows}


@router.get("/positions/{decision_id}/explain")
def explain_position(decision_id: str, user: AuthContext = Depends(get_current_user)):
    """Faz 268-sonrası — kullanıcı isteği: "hangi ajandan ne karar geldiğini
    gösteren açıklayan bir fonksiyon." decisions.agent_contributions'ta
    bu bilginin TAMAMI zaten kayıtlı (her ajanın gerçek AgentOpinion'ı +
    council belief + debate/itiraz sonucu + InnerCritic + DecisionFusion
    gerekçesi) — burada tabloda tek bir JSON blob olarak gömülü kalmak
    yerine, dashboard'un kullanabileceği ayrı bölümlere ayrıştırılıyor."""
    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(decision_id)

    if row is None:
        raise HTTPException(status_code=404, detail="decision_not_found")

    contributions = row.get("agent_contributions") or []
    agent_votes = [item for item in contributions if isinstance(item, dict) and "domain" in item]
    weight_snapshot = next((i["data"] for i in contributions if isinstance(i, dict) and i.get("type") == "weight_snapshot"), None)
    council_belief = next((i["data"] for i in contributions if isinstance(i, dict) and i.get("type") == "council_belief"), None)
    debate_result = next((i["data"] for i in contributions if isinstance(i, dict) and i.get("type") == "debate_result"), None)
    inner_critic = next((i["data"] for i in contributions if isinstance(i, dict) and i.get("type") == "inner_critic"), None)
    decision_fusion_entries = [i["data"] for i in contributions if isinstance(i, dict) and i.get("type") == "decision_fusion"]
    # FIL Faz C — kullanıcı isteği: cross-asset causal bağlam (Granger
    # causality, BTC/ETH → bu sembol), visibility-only — karara girmedi,
    # sadece hangi kanıtın GÖRÜLDÜĞÜNÜ gösteriyor.
    cross_asset_context = [
        i["data"] for i in contributions if isinstance(i, dict) and i.get("type") == "cross_asset_context"
    ]
    # Kullanıcı isteği (2026-08-31): decision_recorder.py'deki 7 "sessiz"
    # kapı (strategy_regime/signal_persistence/pivot_distance/mae_mfe_
    # bucket/regime_trading/direction_trading/asset_class_trading) artık
    # burada görünür — "neden açılmadı" sorusuna DB kazmadan cevap.
    gate_blocks = [i["data"] for i in contributions if isinstance(i, dict) and i.get("type") == "gate_block"]
    # Faz 397 — kullanıcı isteği: strategy_regime_gate test modunda artık
    # engellemiyor, sadece kaydediyor ("canlıda engellerdi") — tam
    # şeffaflık için ayrı bir alan (gate_blocks ile karıştırılmasın,
    # burada işlem GERÇEKTEN açıldı).
    gate_bypasses_test_mode = [
        i["data"] for i in contributions if isinstance(i, dict) and i.get("type") == "gate_bypassed_test_mode"
    ]
    # Faz 401 — Market State / Direction Katmanı Faz 1: per-sembol piyasa
    # durumu okuması (visibility-only, HİÇBİR kararı etkilemiyor).
    market_state_entries = [
        i["data"] for i in contributions if isinstance(i, dict) and i.get("type") == "market_state"
    ]
    # Faz 394 — kullanıcı isteği: HistoricalAnalogOverrideStage'in
    # belief.strength'i gerçek ampirik win_rate ile override ettiği
    # anlar — tam şeffaflık, "neden bu kadar güvenildi" sorusunun cevabı.
    historical_analog_overrides = [
        i["data"] for i in contributions if isinstance(i, dict) and i.get("type") == "historical_analog_override"
    ]
    # Kullanıcı bulgusu: "%74 güvenli bir ajan varken nihai karar neden
    # %28 çıktı?" — bu indirim MetaStage'in ACT/REDUCE kararından SONRA
    # uygulanıyor (services/orchestrator.py::_apply_portfolio_fusion),
    # tek bir final_confidence sayısı bunu hiç açıklamıyordu.
    portfolio_confidence_discounts = [
        i["data"] for i in contributions if isinstance(i, dict) and i.get("type") == "portfolio_confidence_discount"
    ]

    # Faz 376 — kullanıcı bulgusu (canlı bir PYPLUSDT LONG %65.7 örneği
    # üzerinden, çok detaylı bir inceleme): "LONG kararı var, ama sistemin
    # en güçlü kanıt kaynakları büyük ölçüde susturulmuş — bunu görmenin
    # yolu yoktu." Her yönde (LONG/SHORT) TOPLAM effective_influence'ı,
    # hiç ayarlanmamış ("aktif") ajanlarla en az bir ağırlık ayarlaması
    # geçirmiş ("bastırılmış") ajanları ayrı ayrı gösteren bir özet —
    # "kararın gerçek gücünü kim taşıyor, kim sadece susturulmuş"
    # sorusunun tek bakışta cevabı.
    net_evidence_by_direction: dict[str, dict] = {}
    for v in agent_votes:
        direction = v.get("direction")
        if direction not in ("LONG", "SHORT"):
            continue
        bucket = net_evidence_by_direction.setdefault(
            direction, {"total_effective_influence": 0.0, "active_agents": [], "suppressed_agents": []}
        )
        influence = v.get("effective_influence") or 0.0
        bucket["total_effective_influence"] = round(bucket["total_effective_influence"] + influence, 6)
        entry = {"domain": v.get("domain"), "confidence": v.get("confidence"), "effective_influence": influence}
        if v.get("weight_adjustments"):
            bucket["suppressed_agents"].append(entry)
        else:
            bucket["active_agents"].append(entry)
    for bucket in net_evidence_by_direction.values():
        bucket["active_agents"].sort(key=lambda e: -(e["effective_influence"] or 0.0))
        bucket["suppressed_agents"].sort(key=lambda e: -(e["effective_influence"] or 0.0))

    return {
        "id": str(row["id"]),
        "symbol": row["symbol"],
        "final_direction": row["direction"],
        "final_confidence": row.get("confidence"),
        "portfolio_confidence_discounts": portfolio_confidence_discounts,
        "agent_votes": [
            {
                "domain": v.get("domain"),
                "direction": v.get("direction"),
                "confidence": v.get("confidence"),
                # Faz 376 — kullanıcı isteği: "raw confidence → calibrated
                # confidence → reliability weight → regime multiplier →
                # debate penalty → final effective contribution" zincirinin
                # HER adımı — raw_confidence/source_reliability/
                # intrinsic_trust zaten vardı ama açıklama ekranına hiç
                # taşınmıyordu; weight_adjustments (Faz 376, yeni) tam
                # zinciri yapılandırılmış olarak taşıyor.
                "raw_confidence": v.get("raw_confidence"),
                "source_reliability": v.get("source_reliability"),
                "intrinsic_trust": v.get("intrinsic_trust"),
                "effective_influence": v.get("effective_influence"),
                "performance_weight": v.get("performance_weight"),
                "weight_adjustments": v.get("weight_adjustments") or [],
                "evidence": v.get("evidence"),
                "caveats": v.get("caveats"),
            }
            for v in agent_votes
        ],
        "net_evidence_by_direction": net_evidence_by_direction,
        "council_belief": council_belief,
        "debate_result": debate_result,
        "inner_critic": inner_critic,
        "decision_fusion": decision_fusion_entries,
        "cross_asset_context": cross_asset_context,
        "gate_blocks": gate_blocks,
        "gate_bypasses_test_mode": gate_bypasses_test_mode,
        "historical_analog_overrides": historical_analog_overrides,
        "market_state_entries": market_state_entries,
        "weight_snapshot_id": (weight_snapshot or {}).get("id"),
    }


@router.get("/trades")
def list_closed_trades(
    limit: int = 100, offset: int = 0, experiment_bucket: str | None = None,
    user: AuthContext = Depends(get_current_user),
):
    """Faz 224: kritik bulgu — "summary" artık `limit`'e (tablo için kaç
    satır gösterileceği) bağlı DEĞİL, gerçek toplam üzerinden hesaplanıyor
    (closed_trades_summary — /performance'ın all_time'ıyla AYNI sorgu).
    `trades` listesi hâlâ `limit` ile sınırlı (tabloyu 10 binlerce satır
    render etmemek için) ama bu artık sadece görüntüleme sınırı, istatistik
    kaynağı değil.

    Faz 362-devam — kullanıcı isteği: "kör gidiyorum, geriye dönüp
    inceleme yapamıyorum" — `offset` eklendi, GET /positions'la (Faz
    268y) AYNI gerçek sayfalama deseni. `summary.count` her zaman
    gerçek toplamı yansıttığı için frontend sayfa sayısını hesaplayabiliyor.

    Faz 406-devam — kullanıcı bulgusu: "kapanmış işlemlerde pump-fade
    işlemlerini göremiyorum." Kök neden: pump_fade_v1 burada KOŞULSUZ
    dışlanıyordu (ana dashboard istatistiklerinin mekanik bir deneyle
    kirlenmemesi için, Faz 268-sonrası) — bu, Transactions.tsx'teki
    "Pump-Fade" filtresini de sessizce ölü bırakmıştı (her zaman sıfır
    sonuç). `experiment_bucket` verilirse dışlamanın YERİNE geçer (SADECE
    o bucket'ı getirir) — varsayılan davranış (dışlama, kirlenme koruması)
    hiç değişmedi, sadece bu bucket'ı özellikle görmek isteyen çağıran
    artık görebiliyor."""
    with SessionFactory.get_session() as session:
        persistor = DecisionPersistor(session)
        excluded_bucket = None if experiment_bucket else "pump_fade_v1"
        rows = persistor.list_closed_trades(
            limit=limit, offset=offset, exclude_experiment_bucket=excluded_bucket,
            experiment_bucket=experiment_bucket,
        )
        trades = [_serialize(r) for r in rows]
        summary = persistor.closed_trades_summary(
            exclude_experiment_bucket=excluded_bucket, experiment_bucket=experiment_bucket,
        )
        return {
            "trades": trades,
            "summary": {
                "count": summary["trade_count"],
                "win_rate": summary["win_rate"],
                "total_pnl": summary["total_pnl"],
                "tp_count": summary["tp_count"],
                "sl_count": summary["sl_count"],
                "manual_count": summary["manual_count"],
                "manual_full_count": summary["manual_full_count"],
            },
        }


@router.get("/performance")
def performance_summary(user: AuthContext = Depends(get_current_user)):
    """Faz 215: kullanıcı isteği — "dün ne kadar ROI yapmış, haftalık/
    aylık/yıllık ne olmuş" görebilmek. ROI, kullanıcının Settings'te
    belirlediği starting_capital'a göre (gerçek referans sermaye,
    icat edilmiş bir sayı değil)."""
    with SessionFactory.get_session() as session:
        starting_capital = float(AppSettingsRepository(session).get("starting_capital"))
        persistor = DecisionPersistor(session)
        excluded_bucket = "pump_fade_v1"

        def _bucket(rows):
            result = []
            for r in rows:
                deployed = float(r["deployed_notional"] or 0.0)
                total_pnl = float(r["total_pnl"] or 0.0)
                result.append({
                    "period_start": r["bucket"].isoformat(),
                    "trade_count": r["trade_count"],
                    "total_pnl": total_pnl,
                    "win_rate": (r["wins"] / r["trade_count"]) if r["trade_count"] else 0.0,
                    "roi_pct": (total_pnl / starting_capital) if starting_capital else 0.0,
                    # Faz 215: kullanıcı bulgusu — starting_capital test
                    # amaçlı çok büyük bir sayıya çekilince (ör. 10 milyar),
                    # roi_pct her zaman ~0'a yuvarlanıyor, kazanma oranı ve
                    # PnL negatifken bile — kafa karıştırıcı görünüyordu.
                    # Bu, GERÇEKTEN kullanılan sermayeye (bu dönemde açılan
                    # işlemlerin toplam notional'ı) göre getiri — kasa
                    # büyüklüğünden bağımsız, stratejinin kendi
                    # performansını yansıtıyor.
                    "roi_pct_on_deployed": (total_pnl / deployed) if deployed else 0.0,
                })
            return result

        daily = _bucket(persistor.performance_by_period("day", exclude_experiment_bucket=excluded_bucket))
        weekly = _bucket(persistor.performance_by_period("week", exclude_experiment_bucket=excluded_bucket))
        monthly = _bucket(persistor.performance_by_period("month", exclude_experiment_bucket=excluded_bucket))
        yearly = _bucket(persistor.performance_by_period("year", exclude_experiment_bucket=excluded_bucket))

        # Faz 224: kritik bulgu — burası önceden list_closed_trades(limit=
        # 10000) ile Python'da topluyordu, GET /trades ise limit=100 ile
        # ayrı bir hesap yapıyordu — kullanıcının "işlem sayısı 100
        # görünüyor, Performance'da farklıydı" şikayetinin kök nedeni.
        # Artık ikisi de AYNI, limitsiz SQL agregasyonunu (closed_trades_
        # summary) kullanıyor — tek gerçek kaynak.
        summary = persistor.closed_trades_summary(exclude_experiment_bucket=excluded_bucket)
        total_pnl = summary["total_pnl"]
        deployed_notional = summary["deployed_notional"]

        # Faz 268f — kullanıcı isteği: "kısa/orta/uzun/swing/scalp gibi
        # işlem tiplerinden hangileri başarılı olmuş, dashboard'a otomatik
        # yansısın." limit=100_000 — sayfa boyutuyla değil, GERÇEK
        # toplamla sınırlı (close-profitable'ın kullandığı aynı desen).
        all_closed = persistor.list_closed_trades(limit=100_000, exclude_experiment_bucket=excluded_bucket)
        type_buckets: dict[str, dict] = {}
        for row in all_closed:
            trade_type = _classify_trade_type(row)
            if trade_type is None:
                continue
            bucket = type_buckets.setdefault(trade_type, {"trade_count": 0, "wins": 0, "total_pnl": 0.0})
            pnl = float(row.get("pnl") or 0.0)
            bucket["trade_count"] += 1
            bucket["total_pnl"] += pnl
            if pnl > 0:
                bucket["wins"] += 1
        by_trade_type = {
            trade_type: {
                "trade_count": b["trade_count"],
                "win_rate": (b["wins"] / b["trade_count"]) if b["trade_count"] else 0.0,
                "total_pnl": round(b["total_pnl"], 2),
            }
            for trade_type, b in type_buckets.items()
        }

        return {
            "starting_capital": starting_capital,
            "all_time": {
                "trade_count": summary["trade_count"],
                "total_pnl": total_pnl,
                "win_rate": summary["win_rate"],
                "roi_pct": (total_pnl / starting_capital) if starting_capital else 0.0,
                "roi_pct_on_deployed": (total_pnl / deployed_notional) if deployed_notional else 0.0,
                "deployed_notional": deployed_notional,
                # Faz 238: kullanıcı isteği — "kirli geçmiş veriyi
                # temizle." Aşırı-capital test döneminden kalan, gerçek
                # olmayan notional'lı işlemler (excluded_from_stats=true)
                # istatistiklerden hariç tutuluyor — silinmiyor, sadece
                # şeffaflık için kaç tanesinin hariç tutulduğu gösteriliyor.
                "excluded_dirty_trades_count": summary["excluded_count"],
                "tp_count": summary["tp_count"],
                "sl_count": summary["sl_count"],
                "manual_count": summary["manual_count"],
                "manual_full_count": summary["manual_full_count"],
            },
            "daily": daily,
            "weekly": weekly,
            "monthly": monthly,
            "yearly": yearly,
            "by_trade_type": by_trade_type,
            "by_direction": persistor.closed_trades_summary_by_direction(
                exclude_experiment_bucket=excluded_bucket
            ),
            # Faz 400-devam — kullanıcı isteği: canonical evaluation cohort
            # görünürlüğü. `by_trade_type` yukarıdaki `all_time` (limitsiz
            # closed_trades_summary SQL agregasyonu) İLE AYNI kaynaktan
            # DEĞİL, ayrı bir list_closed_trades(limit=100_000) çağrısından
            # geliyor -- bugün pratikte eşit ama gerçek toplam 100.000'i
            # geçerse SESSİZCE ayrışabilirdi. Bu alan hangi pencereden
            # geldiğini açıkça gösteriyor.
            "by_trade_type_evaluation_window": describe_evaluation_window(
                all_closed, limit=100_000, exclude_experiment_buckets=[excluded_bucket] if excluded_bucket else [],
            ),
        }


@router.post("/positions/close-due")
def close_due_positions(
    user: AuthContext = Depends(require_role(Role.OPERATOR)),
):
    """Prod'da celery beat periyodik çalıştırır (close_due_positions_task);
    bu endpoint manuel tetikleme ve test için. Faz 265: hold_seconds
    parametresi kaldırıldı — Faz 215'ten beri PositionCloser bunu zaten
    hiç kullanmıyordu (pozisyonlar sadece gerçekten stop/hedefe/
    likidasyona ulaşınca kapanıyor, süre yüzünden asla)."""
    closer = PositionCloser(RoutingProvider())
    with SessionFactory.get_session() as session:
        closed = closer.close_due_positions(DecisionPersistor(session))
    return {"closed_count": len(closed), "closed": closed}


@router.post("/positions/pump-fade/cleanup-stale")
def cleanup_stale_pump_fade_positions(
    cutoff: datetime | None = None,
    dry_run: bool = False,
    user: AuthContext = Depends(require_role(Role.ADMIN)),
):
    """Faz 279/2026-08-28 — pump_fade_v1 deneyinin eski, hâlâ açık kalmış
    pozisyonlarını temizler. Bu satırlar silinmez, gerçek audit trail korunur;
    sadece status='closed', excluded_from_stats=true işaretlenir ve dashboard
    toplamlarına karışmazlar. `dry_run=true` ile sadece etki önizlemesi
    döndürülür, gerçek kapanış yapılmaz."""
    cutoff_at = cutoff or datetime(2026, 8, 19, 8, 21, 15, tzinfo=UTC)
    with SessionFactory.get_session() as session:
        repo = DecisionPersistor(session)
        stale_rows = [
            row for row in repo.list_open_positions_for_experiment("pump_fade_v1")
            if row.get("opened_at") is not None and row["opened_at"] < cutoff_at
        ]
        if dry_run:
            return {
                "dry_run": True,
                "experiment_bucket": "pump_fade_v1",
                "cutoff_at": cutoff_at.isoformat(),
                "stale_count": len(stale_rows),
                "decision_ids": [str(row["id"]) for row in stale_rows],
            }

        prices = _fetch_current_prices({row["symbol"] for row in stale_rows})
        closed = repo.close_stale_positions_for_experiment(
            "pump_fade_v1",
            cutoff_at=cutoff_at,
            current_prices=prices,
            exit_reason="legacy_cleanup",
        )
        return {
            "dry_run": False,
            "experiment_bucket": "pump_fade_v1",
            "cutoff_at": cutoff_at.isoformat(),
            "stale_count": len(stale_rows),
            "closed_count": len(closed),
            "closed": closed,
        }


class PartialCloseRequest(BaseModel):
    fraction: float


@router.post("/positions/{decision_id}/partial-close")
def partial_close_position(
    decision_id: str,
    body: PartialCloseRequest,
    user: AuthContext = Depends(require_role(Role.OPERATOR)),
):
    """Faz 268 — kullanıcı isteği: "aşamalı kapama, pozisyonun yarısını/
    çeyreğini kademeli kapatabilen mekanizma." fraction=0.5 açık miktarın
    yarısını, 0.25 çeyreğini gerçek güncel fiyattan realize eder; pozisyon
    'open' kalır, sadece quantity azalır. fraction=1.0 kalanın tamamını
    kapatır (gerçek bir tam kapanış)."""
    closer = PositionCloser(RoutingProvider())
    with SessionFactory.get_session() as session:
        try:
            result = closer.close_partial(DecisionPersistor(session), decision_id, body.fraction)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
    return result


def _scan_profitable_positions(closer: PositionCloser) -> dict:
    """Faz 367-devam — kullanıcı isteği: "toplu kapat" butonuna basmadan
    ÖNCE ne kadar net PnL realize edileceğini görmek istiyorum. Hem
    önizleme (GET, hiçbir şey kapatmaz) hem gerçek kapatma (POST) AYNI
    tarama/tahmin döngüsünü paylaşıyor — ikisi arasında sessizce sapan
    iki ayrı hesap olmasın diye. Görünen sayfa (limit=100) ile sınırlı
    DEĞİL — TÜM açık pozisyonlar taranır (Faz 268p'nin orijinal notu)."""
    with SessionFactory.get_session() as session:
        persistor = DecisionPersistor(session)
        positions = persistor.list_open_positions(limit=100_000)

    prices = _fetch_current_prices({p["symbol"] for p in positions})

    profitable = []
    skipped_unprofitable = 0
    skipped_no_price = 0
    for pos in positions:
        price = prices.get(pos["symbol"])
        if price is None:
            skipped_no_price += 1
            continue
        estimated_net_pnl = closer.estimate_net_pnl_if_closed_now(pos, price)
        if estimated_net_pnl <= 0:
            skipped_unprofitable += 1
            continue
        profitable.append({"decision_id": str(pos["id"]), "symbol": pos["symbol"], "estimated_pnl": estimated_net_pnl})

    return {"profitable": profitable, "skipped_unprofitable": skipped_unprofitable, "skipped_no_price": skipped_no_price}


@router.get("/positions/close-profitable/preview")
def preview_close_profitable_positions(
    user: AuthContext = Depends(require_role(Role.OPERATOR)),
):
    """Kullanıcı isteği (2026-08-28): "Kârdakileri Toplu Kapat" butonuna
    basmadan önce ne kadar PnL realize edileceğini göster." Read-only —
    hiçbir pozisyon kapatılmaz, sadece POST'un kullanacağı AYNI tahmini
    döndürür."""
    closer = PositionCloser(RoutingProvider())
    scan = _scan_profitable_positions(closer)
    return {
        "count": len(scan["profitable"]),
        "total_pnl": sum(p["estimated_pnl"] for p in scan["profitable"]),
        "skipped_unprofitable": scan["skipped_unprofitable"],
        "skipped_no_price": scan["skipped_no_price"],
    }


@router.post("/positions/close-profitable")
def close_profitable_positions(
    user: AuthContext = Depends(require_role(Role.OPERATOR)),
):
    """Faz 268p — kullanıcı isteği: "kârda olan pozisyonları toplu kapatma
    butonu... komisyona ezilmeyecek şekilde karda ise kapansınlar."
    Kapatmadan ÖNCE her pozisyon için güncel fiyatla net (komisyon
    düşülmüş) kâr tahmini hesaplanır — SADECE pozitif çıkanlar gerçekten
    kapatılır. Kapanış işlemi geri alınamaz olduğu için (services/
    position_closer.py::close_partial fraction=1.0 çağrısı DB'yi hemen
    günceller), önce filtrelemek zorunlu — "kapat, zarardaysa geri al"
    diye bir şey yok."""
    closer = PositionCloser(RoutingProvider())
    scan = _scan_profitable_positions(closer)

    closed = []
    for pos in scan["profitable"]:
        with SessionFactory.get_session() as session:
            try:
                result = closer.close_partial(DecisionPersistor(session), pos["decision_id"], 1.0)
            except ValueError:
                continue
        closed.append({"decision_id": pos["decision_id"], "symbol": pos["symbol"], "pnl": result["pnl"]})

    return {
        "closed_count": len(closed),
        "closed": closed,
        "skipped_unprofitable": scan["skipped_unprofitable"],
        "skipped_no_price": scan["skipped_no_price"],
    }
