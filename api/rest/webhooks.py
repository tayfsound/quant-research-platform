"""Inbound webhook receiver'lar — Faz 185.

TradingView klasik "API key alıp veri çek" modeliyle çalışmıyor: Pine Script
alert'leri, alarm tetiklendiğinde bizim belirlediğimiz bir URL'e HTTP POST
gönderiyor (inbound). Bu yüzden bu endpoint `require_role`/JWT kullanmıyor —
TradingView'ın bize Authorization header'ı gönderme imkanı yok. Bunun yerine
alert mesajının JSON gövdesine gömülen paylaşılan bir secret doğrulanıyor
(TRADINGVIEW_WEBHOOK_SECRET boşsa, SECRET_KEY/ADMIN_SETUP_TOKEN'la aynı
"dev modu" konvansiyonuyla, doğrulama atlanır).
"""
from fastapi import APIRouter, Depends, HTTPException, Request

from config import get_settings
from database.repositories.external_signal_repository import ExternalSignalRepository
from database.session_factory import SessionFactory
from services.auth_service import AuthContext, get_current_user

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/tradingview")
async def tradingview_webhook(request: Request):
    payload = await request.json()

    expected_secret = get_settings().TRADINGVIEW_WEBHOOK_SECRET
    if expected_secret and payload.get("secret") != expected_secret:
        raise HTTPException(status_code=403, detail="invalid_webhook_secret")

    symbol = payload.get("symbol")
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol_required")

    stored_payload = {k: v for k, v in payload.items() if k != "secret"}

    with SessionFactory.get_session() as session:
        signal_id = ExternalSignalRepository(session).save(
            source="tradingview",
            symbol=symbol,
            signal=payload.get("signal"),
            payload=stored_payload,
        )

    return {"id": str(signal_id), "status": "received", "symbol": symbol}


@router.get("/tradingview/recent")
async def recent_tradingview_signals(
    symbol: str | None = None,
    limit: int = 50,
    user: AuthContext = Depends(get_current_user),
):
    with SessionFactory.get_session() as session:
        rows = ExternalSignalRepository(session).get_recent(symbol=symbol, limit=limit)
        return {
            "signals": [
                {
                    "id": str(r["id"]),
                    "time": r["time"].isoformat(),
                    "symbol": r["symbol"],
                    "signal": r["signal"],
                    "payload": r["payload"],
                }
                for r in rows
            ]
        }
