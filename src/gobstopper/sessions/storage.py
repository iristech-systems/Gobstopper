"""
Session storage backends for Gobstopper
"""
import abc
import os
import pickle
import time
from pathlib import Path
from typing import Optional, Dict, Any, Awaitable

SESSION_EXPIRATION_TIME = 3600 * 24 * 7  # 1 week

class BaseSessionStorage(abc.ABC):
    """Abstract base class for session storage."""

    @abc.abstractmethod
    def load(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load a session from storage."""
        raise NotImplementedError

    @abc.abstractmethod
    def save(self, session_id: str, data: Dict[str, Any]):
        """Save a session to storage."""
        raise NotImplementedError

    @abc.abstractmethod
    def delete(self, session_id: str):
        """Delete a session from storage."""
        raise NotImplementedError

    @abc.abstractmethod
    def cleanup(self):
        """Clean up expired sessions."""
        raise NotImplementedError


class AsyncBaseSessionStorage(abc.ABC):
    @abc.abstractmethod
    async def load(self, session_id: str) -> Optional[Dict[str, Any]]: ...
    @abc.abstractmethod
    async def save(self, session_id: str, data: Dict[str, Any]) -> None: ...
    @abc.abstractmethod
    async def delete(self, session_id: str) -> None: ...
    async def cleanup(self) -> None: ...

# Utility for middleware
async def maybe_await(result):
    if hasattr(result, "__await__"):
        return await result
    return result


class FileSessionStorage(BaseSessionStorage):
    """File-based session storage."""

    def __init__(self, directory: Path):
        self.directory = directory
        if not self.directory.exists():
            self.directory.mkdir(parents=True, exist_ok=True)

    def load(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load session data from a file."""
        filepath = self.directory / session_id
        if not filepath.exists():
            return None

        try:
            with open(filepath, 'rb') as f:
                session_data = pickle.load(f)

            if session_data.get('expires_at', 0) < time.time():
                self.delete(session_id)
                return None

            return session_data.get('data')
        except (pickle.UnpicklingError, FileNotFoundError):
            return None

    def save(self, session_id: str, data: Dict[str, Any]):
        """Save session data to a file."""
        filepath = self.directory / session_id
        session_data = {
            'data': data,
            'expires_at': time.time() + SESSION_EXPIRATION_TIME
        }
        with open(filepath, 'wb') as f:
            pickle.dump(session_data, f)

    def delete(self, session_id: str):
        """Delete a session file."""
        filepath = self.directory / session_id
        if filepath.exists():
            filepath.unlink()

    def cleanup(self):
        """Remove expired session files."""
        now = time.time()
        for filepath in self.directory.iterdir():
            try:
                with open(filepath, 'rb') as f:
                    session_data = pickle.load(f)
                if session_data.get('expires_at', 0) < now:
                    filepath.unlink()
            except (pickle.UnpicklingError, FileNotFoundError):
                # Ignore corrupted or missing files
                pass
