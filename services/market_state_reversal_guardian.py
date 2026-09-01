"""Market State Reversal Guardian — Faz 403 (Market State Katmanı Faz 3,
bkz. ~/.claude/plans/velvety-whistling-parasol.md).

`services/regime_reversal_guardian.py` (Faz 352, yön-bazlı: sistem
genelinde bir yönde ardışık stop-loss eşiği aşılırsa o yönde yeni giriş
durdurur) ve `services/belief_reversal_exit.py` (Faz 362, sembol-bazlı:
council'in KENDİ inancı 6 ardışık kez güvenle ters dönerse pozisyonu
erken kapatır) İLE AYNI ailede, ama İKİSİNDEN DE FARKLI, TAMAMLAYICI bir
sinyal: bu ikisi REAKTİF — sadece kanıt (stop serisi, council'in kendi
sürekli ters oyu) zaten biriktikten SONRA harekete geçiyorlar.

Gerçek bulgu (bu oturumda, Concept Drift/XAUTUSDT araştırması): 27-31
Ağustos'taki gerçek kayıp serisi boyunca council'in KENDİ inancı hiçbir
zaman ters yöne dönmedi (sürekli zayıf LONG) — belief_reversal_exit
yapısal olarak kurtaramazdı, tetiklenecek bir sinyal hiç oluşmadı. Daha
geniş kontrol: son 80 kayıp kararın %46'sında AI'nin yönü, pozisyon
açıkken BİR KEZ BİLE güvenle karşı yöne dönmedi. Bu modül, council'in
HENÜZ fark etmediği bir dönüşü, piyasanın KENDİ istatistiksel okumasından
(market_state_engine.py::compute_market_state()'in `reversing` sinyali,
Welch t-test) proaktif olarak yakalıyor — council'in inancından TAMAMEN
BAĞIMSIZ bir kanıt kaynağı.

Kasıtlı olarak ihtiyatlı: TAM kapatma değil, kısmi (%50) — belief_
reversal_exit de 3619 pozisyonluk gerçek doğrulamadan SONRA tam kapatmaya
güvenmişti, bu mekanizma henüz o kanıta sahip değil. Varsayılan KAPALI
(feedback_incremental_module_activation)."""
_MECHANICAL_EXPERIMENT_BUCKETS = {"pump_fade_v1", "basis_arb_v1"}
_PARTIAL_CLOSE_FRACTION = 0.5


def _load_settings() -> tuple[bool, float]:
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        enabled = repo.get("market_state_reversal_guardian_enabled") == "true"
        min_confidence = float(repo.get("market_state_reversal_guardian_min_confidence"))
    return enabled, min_confidence


def find_reversal_triggered_positions(min_confidence: float) -> list[dict]:
    """GERÇEK açık pozisyonları (mekanik stratejiler hariç — kendi risk
    yönetimlerine sahipler) tarar, her biri için en son kaydedilmiş
    market_state_snapshots raporunda o sembolün GERÇEKTEN `reversing`
    olup olmadığına, yönünün pozisyonun TERSİ olup olmadığına ve
    güveninin eşiği geçip geçmediğine bakar. Rapor hiç yoksa (henüz
    hiç periyodik görev çalışmadıysa) ya da sembol raporda yoksa
    fail-closed: o pozisyon hiç tetiklenmez — icat edilmiş bir market
    state asla üretilmez. Tetiklenenleri döner — kapatma İÇERMİYOR
    (saf tarama, test edilebilir)."""
    from database.repositories.decision_persistor import DecisionPersistor
    from database.repositories.market_state_report_repository import MarketStateReportRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        persistor = DecisionPersistor(session)
        positions = persistor.list_open_positions(limit=None)
        positions = [
            p for p in positions
            if p.get("experiment_bucket") not in _MECHANICAL_EXPERIMENT_BUCKETS
            and (p.get("direction") or "").upper() in ("LONG", "SHORT")
        ]
        report = MarketStateReportRepository(session).get_latest()

    by_symbol = ((report or {}).get("result") or {}).get("by_symbol") or {}
    triggered = []
    for pos in positions:
        state = by_symbol.get(pos["symbol"])
        if not state or not state.get("reversing"):
            continue
        state_direction = state.get("direction")
        pos_direction = (pos.get("direction") or "").upper()
        if state_direction not in ("LONG", "SHORT") or state_direction == pos_direction:
            continue
        if (state.get("confidence") or 0.0) < min_confidence:
            continue
        triggered.append({**pos, "market_state": state})
    return triggered


def sweep_market_state_reversals() -> dict:
    """Periyodik Celery görevinden çağrılır (bkz. services/tasks.py::
    market_state_reversal_guardian_task). Kapalıyken sıfır maliyetli
    no-op — idempotent: zaten kısmen/tamamen kapatılmış pozisyonlar için
    tekrar çağrılması zararsız."""
    enabled, min_confidence = _load_settings()
    if not enabled:
        return {"enabled": False}

    triggered = find_reversal_triggered_positions(min_confidence)
    if not triggered:
        return {"enabled": True, "min_confidence": min_confidence, "closed": []}

    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory
    from market_data.ingestion.data_provider import RoutingProvider
    from services.position_closer import PositionCloser

    closer = PositionCloser(RoutingProvider())
    closed = []
    for pos in triggered:
        with SessionFactory.get_session() as session:
            try:
                result = closer.close_partial(
                    DecisionPersistor(session), str(pos["id"]), _PARTIAL_CLOSE_FRACTION,
                    exit_reason="market_state_reversal",
                )
            except ValueError:
                continue
        closed.append({
            "symbol": pos["symbol"], "direction": pos["direction"],
            "market_state_direction": pos["market_state"]["direction"],
            "market_state_confidence": pos["market_state"]["confidence"],
            "pnl": result["pnl"],
        })

    if closed:
        import structlog
        structlog.get_logger().warning(
            "market_state_reversal_triggered", min_confidence=min_confidence, closed_count=len(closed),
        )

    return {
        "enabled": True, "min_confidence": min_confidence,
        "triggered_count": len(triggered), "closed": closed,
    }
