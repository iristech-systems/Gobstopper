# src/wopr/sessions/memory_storage.py
import time
from typing import Dict, Any, Optional, Tuple

from .storage import AsyncBaseSessionStorage, SESSION_EXPIRATION_TIME

class MemorySessionStorage(AsyncBaseSessionStorage):
    """
    An in-memory session storage backend for development and testing.
    This storage is volatile and will be cleared when the application restarts.
    """

    def __init__(self, ttl: int = SESSION_EXPIRATION_TIME):
        self._sessions: Dict[str, Tuple[Dict[str, Any], float]] = {}
        self.ttl = ttl

    async def load(self, session_id: str) -> Optional[Dict[str, Any]]:
        session = self._sessions.get(session_id)
        if not session:
            return None

        data, expires_at = session
        if time.time() > expires_at:
            # Session has expired, delete it
            await self.delete(session_id)
            return None

        return data

    async def save(self, session_id: str, data: Dict[str, Any]) -> None:
        expires_at = time.time() + self.ttl
        self._sessions[session_id] = (data, expires_at)

    async def delete(self, session_id: str) -> None:
        if session_id in self._sessions:
            del self._sessions[session_id]

    async def cleanup(self) -> None:
        now = time.time()
        expired_sessions = [
            sid for sid, (_, expires_at) in self._sessions.items() if now > expires_at
        ]
        for sid in expired_sessions:
            await self.delete(sid)
