"""Binance WebSocket stream handler."""
import asyncio
import json
from collections.abc import Awaitable, Callable

import websockets


class BinanceWebSocket:
    def __init__(self, on_message: Callable[[dict], Awaitable[None]]):
        self._on_message = on_message
        self._ws = None

    async def connect(self, streams: list[str]):
        url = f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}"
        self._ws = await websockets.connect(url)
        asyncio.create_task(self._listen())

    async def _listen(self):
        async for msg in self._ws:
            await self._on_message(json.loads(msg))

    async def close(self):
        if self._ws:
            await self._ws.close()
