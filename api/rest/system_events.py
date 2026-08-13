"""System Events API — Faz 269 (Cognitive Core 2.0 / M1) Veri ve olay
altyapısı. database/repositories/event_log_repository.py'nin ürettiği,
sistemdeki önemli olayların (ör. kill switch tetiklenmesi) birleşik zaman
çizelgesi."""
from fastapi import APIRouter, Depends

from database.repositories.event_log_repository import EventLogRepository
from database.session_factory import SessionFactory
from services.auth_service import AuthContext, get_current_user

router = APIRouter(prefix="/system-events", tags=["system-events"])


@router.get("/")
async def system_events(
    event_type: str | None = None,
    limit: int = 100,
    user: AuthContext = Depends(get_current_user),
):
    with SessionFactory.get_session() as session:
        events = EventLogRepository(session).list_events(event_type=event_type, limit=limit)
    return {"events": events}
