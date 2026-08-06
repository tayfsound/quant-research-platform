"""Canlı tahminleri dashboard'a WebSocket ile gönderir.

Gap #18: bu endpoint eskiden `random.choice`/`random.uniform` ile tamamen
uydurma veri üretiyordu — dashboard'un "Live AI Predictions" view'ı gerçek
bir modelin çıktısı gibi gösteriyordu ama arkasında hiçbir gerçek karar yoktu.

Faz 215: kullanıcı bulgusu — "sadece BTC var, sistemdeki bütün tokenları
otomatik eklemiyor, her yeni token eklediğimizde manuel eklemek zorunda
kalmayalım." Kök neden: her tick'te tek bir CognitiveOrchestrator.
run_cycle() (sembol verilmeden, varsayılana düşüyor) çalıştırılıyordu.
Bunu watchlist'teki TÜM semboller için tekrar tekrar (2sn'de bir) çalıştırmak
hem çok pahalı olurdu (embedding + gerçek API çağrıları x15 sembol x her
2sn) hem de zaten Celery'nin run_trading_cycle_task'ının (120sn'de bir,
TÜM watchlist için) yaptığı işi gereksiz yere tekrarlardı. Bunun yerine
api/rest/tokens.py::build_tokens_list() ile AYNI, zaten hesaplanmış gerçek
veriyi (decisions tablosundaki en son karar, sembol başına) okuyor —
watchlist'e yeni bir sembol eklenince otomatik olarak burada da görünür,
kod değişikliği gerekmez."""
import asyncio

from fastapi import APIRouter, WebSocket

from api.rest.tokens import build_tokens_list
from database.session_factory import SessionFactory

router = APIRouter()


@router.websocket("/stream/live")
async def live_stream(websocket: WebSocket):
    await websocket.accept()
    while True:
        await asyncio.sleep(3)
        with SessionFactory.get_session() as session:
            tokens = build_tokens_list(session)
        await websocket.send_json({"tokens": tokens})
