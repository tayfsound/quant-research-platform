"""Faz 188: gerçek açık pozisyon sayısı + kullanılan sermaye yüzdesi —
RiskEngine'in concurrent-position/capital-% kontrolleri, ve trading_mode
(test/live) için tek gerçek kaynak. Hash-imzalı risk_limits'ten (faz172)
kasıtlı olarak ayrı: bunlar kullanıcının günlük ayarlayabildiği operasyonel
tercihler (app_settings), kriptografik acil durum eşiği değil."""
from datetime import UTC, datetime

from analytics.concept_drift import compute_concept_drift
from contracts.contexts.risk import RiskReason
from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

_CONCEPT_DRIFT_WIN_RATE_DROP_THRESHOLD = 0.15


def get_concept_drift_diagnostics(decision_repo: DecisionPersistor, min_opened_at: datetime | None = None) -> dict:
    """Faz 268-sonrası — kullanıcı isteği: "Concept Drift aktif olduğunda
    panelden göreyim, neden pozisyon almadığını bilmeden kalmayayım."
    _compute_concept_drift_reason (aşağıda) SADECE tetiklendiğinde bir
    RiskReason döner — dashboard'un HER ZAMAN (tetiklenmemişken de) gerçek
    sayıları gösterebilmesi için bu, ALTTAKI ham veriyi/kararı ayrıştırıp
    döndüren, tek kaynak fonksiyon (ikisi de AYNI eşikleri kullanıyor,
    kopya/çelişkili mantık riski yok).

    pump_fade_v1 (bkz. services/pump_fade_strategy.py) hariç tutuluyor —
    AI'ın karar/confidence sisteminden tamamen yalıtık, kendi (çok farklı)
    kâr/zarar dağılımına sahip mekanik bir strateji; onun kapanışları AI'ın
    kazanma oranı istatistiğine karışırsa Concept Drift AI'ın gerçekte
    bozulmadığı bir anda yanlışlıkla tetiklenebilir.

    Faz 383 — kullanıcı isteği: "tetiklendi diye sonsuza kadar bırakacak
    değiliz, dashboard'daki uyarı balonuna kapatma butonu gelsin." Bu
    kontrol saf bir HESAPLAMA (son 150 kapanmış işlem) — kalıcı bir "aktif/
    kapalı" durumu YOK, bu yüzden basit bir on/off flag'i çalışmaz (bir
    sonraki cycle'da işlemler değişmeden aynı 150'lik pencere aynı sonucu
    üretir, "kapatma" anlamsız kalırdı). min_opened_at, kill_switch_
    legacy_cutoff_at İLE AYNI, zaten kanıtlanmış desen (bkz. list_closed_
    trades'in min_opened_at yorumu): insan "sıfırla" dediğinde bu tarihten
    ÖNCE açılmış pozisyonlar pencereye hiç girmiyor — istatistik SAHTE
    hale getirilmiyor (eski kötü işlemler silinmiyor/gizlenmiyor, sadece
    "bundan sonrasına bak" deniyor), ve performans GERÇEKTEN düzelmediyse
    yeterli taze veri birikince drift dürüstçe TEKRAR tetiklenir."""
    trades = decision_repo.list_closed_trades(
        limit=150, exclude_experiment_bucket=PUMP_FADE_EXPERIMENT_BUCKET, min_opened_at=min_opened_at,
    )
    if len(trades) < 100:
        return {"available": False, "sample_size": len(trades), "required_sample_size": 100}

    recent_outcomes = [(t.get("pnl") or 0.0) > 0 for t in trades[:50]]
    baseline_outcomes = [(t.get("pnl") or 0.0) > 0 for t in trades[50:150]]
    drift = compute_concept_drift(baseline_outcomes, recent_outcomes)
    if drift is None:
        return {"available": False, "sample_size": len(trades), "required_sample_size": 100}

    win_rate_drop = round(drift["baseline_win_rate"] - drift["recent_win_rate"], 4)
    active = drift["drift_detected"] and win_rate_drop >= _CONCEPT_DRIFT_WIN_RATE_DROP_THRESHOLD
    return {
        "available": True,
        "active": active,
        "baseline_win_rate": drift["baseline_win_rate"],
        "recent_win_rate": drift["recent_win_rate"],
        "win_rate_drop": win_rate_drop,
        "p_value": drift["p_value"],
    }


def _compute_concept_drift_reason(decision_repo: DecisionPersistor, min_opened_at: datetime | None = None) -> RiskReason | None:
    """Faz 268-sonrası — bkz. contracts/contexts/risk.py::concept_drift_
    reason yorumu. Burada (RiskEngine.execute()'un İÇİNDE DEĞİL) hesaplanır
    ki test çağıranlar ctx.risk.concept_drift_reason'ı doğrudan set edip
    RiskEngine'i izole test edebilsin — gerçek bir regresyon (2026-08-13)
    bu ayrımın neden zorunlu olduğunu kanıtladı."""
    diagnostics = get_concept_drift_diagnostics(decision_repo, min_opened_at=min_opened_at)
    if not diagnostics["available"] or not diagnostics["active"]:
        return None

    return RiskReason(
        code="CONCEPT_DRIFT_DEGRADATION",
        message=(
            f"Kazanma oranı {diagnostics['baseline_win_rate']:.1%}'den "
            f"{diagnostics['recent_win_rate']:.1%}'e düştü (p={diagnostics['p_value']:.4f}, "
            f"istatistiksel olarak anlamlı) — model geçerliliği sorgulanıyor"
        ),
        severity="warning",
    )


def load_position_risk_state(
    symbol: str | None = None,
    timeframe_filter: str | None = None,
    exclude_timeframe: str | None = None,
    capital_pct_override: float | None = None,
    max_concurrent_override: int | None = None,
) -> dict:
    """Faz 259: kullanıcı isteği — orta-vadeli pozisyon katmanı, kısa-vadeli
    ile AYNI sermaye/concurrent-position sayacını paylaşmamalı (biri
    diğerinin kapasitesini tüketmesin).

    timeframe_filter: SADECE bu zaman diliminden açılmış pozisyonlar
    sayılır (orta-vadeli katman kendi payını görsün diye — kesin eşleşme,
    orta-vade henüz yeni olduğu için eski/NULL kayıtlarla karışma riski yok).
    exclude_timeframe: bu zaman diliminden açılmışlar HARİÇ hepsi sayılır
    (kısa-vadeli katman kendi payını görsün diye — bu migration'dan ÖNCE
    açılmış eski pozisyonların timeframe'i NULL'dur, bunlar hâlâ gerçek ve
    hâlâ sermaye tüketiyor, "include" değil "exclude" mantığı kullanmak
    onları yanlışlıkla dışarıda bırakmayı önlüyor).
    capital_pct_override/max_concurrent_override: orta-vadeli katmanın
    kendi (Settings'teki kısa-vadeliden ayrı) ayarlarını kullanabilmesi
    için."""
    with SessionFactory.get_session() as session:
        settings_repo = AppSettingsRepository(session)
        trading_mode = settings_repo.get("trading_mode")
        max_concurrent = max_concurrent_override if max_concurrent_override is not None else int(settings_repo.get("max_concurrent_positions"))
        max_capital_pct = capital_pct_override if capital_pct_override is not None else float(settings_repo.get("max_capital_pct"))
        starting_capital = float(settings_repo.get("starting_capital"))
        # Faz 363 — kullanıcı isteği: "%86 isabet oranı yakalıyor ama 2k
        # dolar zarar ediyor" — dinamik capital_per_trade formülünün
        # (starting_capital*max_capital_pct/max_concurrent_positions)
        # YERİNE geçen, opsiyonel sabit $ tutarı. 0/boş = devre dışı.
        fixed_position_size_usd = float(settings_repo.get("fixed_position_size_usd") or "0")
        ai_enabled = settings_repo.get("ai_enabled") == "true"
        kill_switch_consecutive_losses = int(settings_repo.get("kill_switch_consecutive_losses"))
        legacy_cutoff_raw = settings_repo.get("kill_switch_legacy_cutoff_at")
        legacy_cutoff_at = datetime.fromisoformat(legacy_cutoff_raw) if legacy_cutoff_raw else None
        max_open_per_symbol_direction_raw = settings_repo.get("max_open_positions_per_symbol_direction")
        max_open_per_symbol_direction = (
            int(max_open_per_symbol_direction_raw) if max_open_per_symbol_direction_raw else None
        )
        # Faz 358 — bkz. contracts/contexts/risk.py::max_same_symbol_
        # direction_capital_pct docstring'i.
        max_same_symbol_direction_capital_pct_raw = settings_repo.get("max_same_symbol_direction_capital_pct")
        max_same_symbol_direction_capital_pct = (
            float(max_same_symbol_direction_capital_pct_raw) if max_same_symbol_direction_capital_pct_raw else None
        )

        decision_repo = DecisionPersistor(session)

        # Faz 268-sonrası — kullanıcı isteği: "test modunda çalışmasın, illa
        # olacaksa da sadece canlı modunda aktif olsun." Concept Drift GERÇEK
        # sermayeyi bozuk bir modelle işlem yapmaya devam etmekten koruyor —
        # test modunda gerçek kayıp yok, ve tam da test modunun amacı budur
        # (kötü bir dönemden bile geçip gerçek kapanmış işlem verisi
        # biriktirmek — reduce_threshold'un test modunda gevşetilmesiyle
        # aynı felsefe, bkz. CognitiveEngine.execute() Faz 207 yorumu).
        # get_concept_drift_diagnostics (dashboard'un okuduğu) hâlâ HER
        # zaman gerçek istatistikleri hesaplıyor — sadece gerçek pozisyon
        # engelleme (RiskReason) canlı modla sınırlandı.
        concept_drift_legacy_cutoff_raw = settings_repo.get("concept_drift_legacy_cutoff_at")
        concept_drift_legacy_cutoff_at = (
            datetime.fromisoformat(concept_drift_legacy_cutoff_raw) if concept_drift_legacy_cutoff_raw else None
        )
        concept_drift_reason = (
            _compute_concept_drift_reason(decision_repo, min_opened_at=concept_drift_legacy_cutoff_at)
            if trading_mode == "live" else None
        )

        # Faz 268-sonrası — gerçek olay: XAUTUSDT SHORT x54. bkz.
        # contracts/contexts/risk.py::same_direction_open_counts.
        same_direction_open_counts: dict[str, int] = {}
        same_direction_open_notional: dict[str, float] = {}
        if symbol:
            same_direction_open_counts = decision_repo.count_open_by_symbol_direction(symbol)
            same_direction_open_notional = decision_repo.sum_open_notional_by_symbol_direction(symbol)

        # Kill switch: en son kapanmış işlemlerden (tüm semboller,
        # kronolojik olarak en yeniden en eskiye) geriye doğru, İLK
        # kazançtan önceki ardışık kayıp sayısı.
        #
        # Kritik bulgu (2026-08-12): sabit bir limit (önceden max(50,
        # threshold*2)) gerçek bir seri bu limitten UZUN olduğunda sessizce
        # KESİLİYORDU — gerçek canlı olayda seri 115 iken bu sorgu sadece
        # ilk 50'yi görüp consecutive_losses=50 döndürüyordu (kill switch
        # yine de tetiklendi, threshold 10'du, ama sayı GERÇEĞİ yansıtmıyordu
        # — daha yüksek bir threshold'da bu YANLIŞ NEGATİF'e dönüşebilirdi).
        # Artık kazanca ya da gerçek geçmişin sonuna ulaşana kadar limit
        # katlanarak büyütülüyor — asla sessizce kesilmiyor.
        #
        # Faz 268-sonrası: legacy_cutoff_at set edilmişse (kill_switch_
        # legacy_cutoff_at ayarı), bu tarihten ÖNCE AÇILMIŞ pozisyonlar
        # sayaca hiç girmiyor — bkz. list_closed_trades'in min_opened_at
        # yorumu. Filtre SQL'de uygulandığı için döngünün sonlanma koşulu
        # (len(recent_closed) < fetch_limit) hâlâ doğru çalışıyor: eski
        # kayıtlar zaten sorgudan hiç dönmüyor.
        consecutive_losses = 0
        fetch_limit = max(50, kill_switch_consecutive_losses * 2)
        while True:
            recent_closed = decision_repo.list_closed_trades(
                limit=fetch_limit,
                min_opened_at=legacy_cutoff_at,
                exclude_experiment_bucket=PUMP_FADE_EXPERIMENT_BUCKET,
            )
            consecutive_losses = 0
            found_win = False
            for trade in recent_closed:
                if (trade.get("pnl") or 0.0) > 0:
                    found_win = True
                    break
                consecutive_losses += 1
            if found_win or len(recent_closed) < fetch_limit:
                break
            fetch_limit *= 2

        # Faz 269-sonrası — KRİTİK bulgu: limit=1000 sabitti ama gerçek
        # açık pozisyon sayısı 1000'i çoktan aşmıştı (2631) — open_count/
        # capital_used_pct (max_concurrent_positions ve kapital yüzdesi
        # risk kontrollerinin GİRDİSİ) gerçek maruziyetin yarısından
        # azını görüyordu. limit=None ile artık TÜM açık pozisyonlar
        # sayılıyor.
        open_positions = decision_repo.list_open_positions(limit=None)
        if timeframe_filter is not None:
            open_positions = [p for p in open_positions if p.get("timeframe") == timeframe_filter]
        elif exclude_timeframe is not None:
            open_positions = [p for p in open_positions if p.get("timeframe") != exclude_timeframe]

    open_count = len(open_positions)
    # Faz 330 — kritik bulgu: quantity zaten kaldıraçla çarpılmış (bkz.
    # decision_recorder.py: "quantity = quantity * leverage"), yani
    # entry_price*quantity NOTIONAL'dır, gerçek bağlı SERMAYE değil. Bu
    # kontrol GuardrailStage'in MAX_CAPITAL_PCT tavanının (%100) tek girdisi
    # — leverage'ı hesaba katmadan notional toplamak, kaldıraçlı her
    # pozisyonu gerçek marjininin kat kat üstünde saymak demekti (canlıda
    # yakalandı: %915-980 okunuyordu, gerçek marjin bazlı hesap ~%443'tü —
    # ikisi de pump_fade'in kümülatif tavansız büyümesinden kaynaklanıyordu,
    # bkz. pump_fade_strategy.py::_try_open'daki Faz 330 notu, ama bu
    # hesaplama hatası sorunu olduğundan daha da büyük gösteriyordu).
    # leverage None/0 ise (spot, kaldıraçsız) notional=marjin varsayılır.
    capital_committed = sum(
        (p.get("entry_price") or 0.0) * (p.get("quantity") or 0.0) / (p.get("leverage") or 1.0)
        for p in open_positions
    )
    capital_used_pct = (capital_committed / starting_capital) if starting_capital > 0 else 0.0

    return {
        "trading_mode": trading_mode,
        "open_position_count": open_count,
        "max_concurrent_positions": max_concurrent,
        "capital_used_pct": capital_used_pct,
        "max_capital_pct": max_capital_pct,
        "starting_capital": starting_capital,
        "ai_enabled": ai_enabled,
        "consecutive_losses": consecutive_losses,
        "kill_switch_consecutive_losses": kill_switch_consecutive_losses,
        "same_direction_open_counts": same_direction_open_counts,
        "max_open_positions_per_symbol_direction": max_open_per_symbol_direction,
        "same_direction_open_notional": same_direction_open_notional,
        "max_same_symbol_direction_capital_pct": max_same_symbol_direction_capital_pct,
        "concept_drift_reason": concept_drift_reason,
        "fixed_position_size_usd": fixed_position_size_usd,
    }
