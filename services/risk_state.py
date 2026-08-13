"""Faz 188: gerçek açık pozisyon sayısı + kullanılan sermaye yüzdesi —
RiskEngine'in concurrent-position/capital-% kontrolleri, ve trading_mode
(test/live) için tek gerçek kaynak. Hash-imzalı risk_limits'ten (faz172)
kasıtlı olarak ayrı: bunlar kullanıcının günlük ayarlayabildiği operasyonel
tercihler (app_settings), kriptografik acil durum eşiği değil."""
from datetime import UTC, datetime

from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory


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
        min_seconds_between_trades = int(settings_repo.get("min_seconds_between_trades"))
        ai_enabled = settings_repo.get("ai_enabled") == "true"
        kill_switch_consecutive_losses = int(settings_repo.get("kill_switch_consecutive_losses"))
        legacy_cutoff_raw = settings_repo.get("kill_switch_legacy_cutoff_at")
        legacy_cutoff_at = datetime.fromisoformat(legacy_cutoff_raw) if legacy_cutoff_raw else None

        decision_repo = DecisionPersistor(session)

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
            recent_closed = decision_repo.list_closed_trades(limit=fetch_limit, min_opened_at=legacy_cutoff_at)
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

        open_positions = decision_repo.list_open_positions(limit=1000)
        if timeframe_filter is not None:
            open_positions = [p for p in open_positions if p.get("timeframe") == timeframe_filter]
        elif exclude_timeframe is not None:
            open_positions = [p for p in open_positions if p.get("timeframe") != exclude_timeframe]

        seconds_since_last_trade = None
        if symbol:
            last_opened_at = decision_repo.get_last_opened_at(symbol)
            if last_opened_at is not None:
                now = datetime.now(UTC)
                if last_opened_at.tzinfo is None:
                    seconds_since_last_trade = (now.replace(tzinfo=None) - last_opened_at).total_seconds()
                else:
                    seconds_since_last_trade = (now - last_opened_at).total_seconds()

    open_count = len(open_positions)
    capital_committed = sum(
        (p.get("entry_price") or 0.0) * (p.get("quantity") or 0.0) for p in open_positions
    )
    capital_used_pct = (capital_committed / starting_capital) if starting_capital > 0 else 0.0

    return {
        "trading_mode": trading_mode,
        "open_position_count": open_count,
        "max_concurrent_positions": max_concurrent,
        "capital_used_pct": capital_used_pct,
        "max_capital_pct": max_capital_pct,
        "starting_capital": starting_capital,
        "seconds_since_last_trade": seconds_since_last_trade,
        "min_seconds_between_trades": min_seconds_between_trades,
        "ai_enabled": ai_enabled,
        "consecutive_losses": consecutive_losses,
        "kill_switch_consecutive_losses": kill_switch_consecutive_losses,
    }
