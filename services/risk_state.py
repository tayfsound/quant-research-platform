"""Faz 188: gerçek açık pozisyon sayısı + kullanılan sermaye yüzdesi —
RiskEngine'in concurrent-position/capital-% kontrolleri, ve trading_mode
(test/live) için tek gerçek kaynak. Hash-imzalı risk_limits'ten (faz172)
kasıtlı olarak ayrı: bunlar kullanıcının günlük ayarlayabildiği operasyonel
tercihler (app_settings), kriptografik acil durum eşiği değil."""
from datetime import UTC, datetime

from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory


def load_position_risk_state(symbol: str | None = None) -> dict:
    with SessionFactory.get_session() as session:
        settings_repo = AppSettingsRepository(session)
        trading_mode = settings_repo.get("trading_mode")
        max_concurrent = int(settings_repo.get("max_concurrent_positions"))
        max_capital_pct = float(settings_repo.get("max_capital_pct"))
        starting_capital = float(settings_repo.get("starting_capital"))
        min_seconds_between_trades = int(settings_repo.get("min_seconds_between_trades"))
        ai_enabled = settings_repo.get("ai_enabled") == "true"

        decision_repo = DecisionPersistor(session)
        open_positions = decision_repo.list_open_positions(limit=1000)

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
    }
