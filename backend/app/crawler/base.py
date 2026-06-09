from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal, Callable, Awaitable


@dataclass
class ProgressEvent:
    type: Literal["info", "downloaded", "skipped", "error", "done"]
    message: str
    count: int = 0


@dataclass
class SyncResult:
    downloaded: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


# Async callable that receives progress events; implementations are free to
# forward these to SSE, WebSocket, or just log them.
ProgressCallback = Callable[[ProgressEvent], Awaitable[None]]


class BaseCrawler(ABC):
    @abstractmethod
    async def sync(self, progress: ProgressCallback | None = None) -> SyncResult:
        """
        Download all new files from the portal.
        Re-running must be idempotent: already-known files are skipped.
        """
        ...
