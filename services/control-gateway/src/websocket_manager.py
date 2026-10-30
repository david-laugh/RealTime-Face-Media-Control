"""WebSocket connection manager (Gateway -> Browser push)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Iterable

from fastapi import WebSocket

log = logging.getLogger("gateway.ws")

SEND_TIMEOUT_S = 2.0


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        # Serializes register+snapshot against broadcasts so a new client
        # never receives a broadcast before its initial snapshot.
        self._lock = asyncio.Lock()

    @property
    def count(self) -> int:
        return len(self._clients)

    async def connect(self, ws: WebSocket, snapshot: Iterable[dict[str, Any]]) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
            for msg in snapshot:
                await self._send(ws, msg)
        log.info("client connected (%d total)", self.count)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)
        log.info("client disconnected (%d total)", self.count)

    async def broadcast(self, msg: dict[str, Any]) -> None:
        async with self._lock:
            clients = list(self._clients)
            results = await asyncio.gather(*(self._send(ws, msg) for ws in clients))
            for ws, ok in zip(clients, results):
                if not ok:
                    self._clients.discard(ws)
        log.info("broadcast %s/%s to %d client(s)", msg.get("command"), msg.get("reason"), len(clients))

    @staticmethod
    async def _send(ws: WebSocket, msg: dict[str, Any]) -> bool:
        try:
            await asyncio.wait_for(ws.send_text(json.dumps(msg)), timeout=SEND_TIMEOUT_S)
            return True
        except Exception as exc:  # closed socket, timeout, ...
            log.info("dropping client: %s", exc.__class__.__name__)
            return False
