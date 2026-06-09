from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings
from app.models.file_record import DownloadedFile, FileType
from .base import BaseCrawler, ProgressCallback, ProgressEvent, SyncResult
from .portal_client import PortalClient


def _sanitize_filename(name: str) -> str:
    """Strip characters that are invalid on Windows/Linux paths."""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


async def _noop_progress(_: ProgressEvent) -> None:
    pass


class HttpxCrawler(BaseCrawler):
    """
    Crawls the Altius portal via its REST API using httpx.
    Swap for a PlaywrightCrawler later by implementing BaseCrawler.
    """

    def __init__(
        self,
        settings: Settings,
        session: Session,
        client: PortalClient | None = None,
    ):
        self._settings = settings
        self._session = session
        self._client = client or PortalClient(
            api_base_url=f"{settings.portal_url.rstrip('/')}/api"
                         .replace("fo1.altius.finance", "fo1.api.altius.finance")
        )
        self._data_dir = Path(settings.data_dir)

    async def sync(self, progress: ProgressCallback | None = None) -> SyncResult:
        emit = progress or _noop_progress
        result = SyncResult()

        await emit(ProgressEvent("info", "Logging in to portal…"))
        token = await self._client.login(
            self._settings.portal_username, self._settings.portal_password
        )

        await emit(ProgressEvent("info", "Fetching deal list…"))
        deals = await self._client.list_deals(token)
        await emit(ProgressEvent("info", f"Found {len(deals)} deal(s)"))

        for deal in deals:
            deal_id: int = deal["id"]
            deal_name: str = deal.get("title", f"deal_{deal_id}")

            await emit(ProgressEvent("info", f"Scanning files for '{deal_name}'…"))
            try:
                files = await self._client.list_files(token, deal_id)
            except Exception as exc:
                msg = f"Failed to list files for deal {deal_id}: {exc}"
                await emit(ProgressEvent("error", msg))
                result.errors.append(msg)
                continue

            await emit(ProgressEvent("info", f"  {len(files)} file(s) found"))

            for file_meta in files:
                portal_file_id: int = file_meta["id"]
                filename: str = _sanitize_filename(file_meta.get("name", f"file_{portal_file_id}"))
                file_url: str = file_meta.get("file_url", "")
                section_id: int | None = file_meta.get("section_id")

                # --- Idempotency check ---
                existing = (
                    self._session.query(DownloadedFile)
                    .filter_by(portal_file_id=portal_file_id)
                    .first()
                )
                if existing:
                    result.skipped += 1
                    continue

                # --- Download ---
                dest = self._data_dir / f"deal_{deal_id}" / f"{portal_file_id}_{filename}"
                try:
                    if not file_url:
                        raise ValueError("No file_url in portal response")
                    await self._client.download_file(file_url, dest)
                except Exception as exc:
                    msg = f"Download failed for {filename} (id={portal_file_id}): {exc}"
                    await emit(ProgressEvent("error", msg))
                    result.errors.append(msg)
                    continue

                file_hash = _sha256(dest)

                record = DownloadedFile(
                    portal_file_id=portal_file_id,
                    file_hash=file_hash,
                    portal_deal_id=str(deal_id),
                    deal_name=deal_name,
                    filename=filename,
                    file_path=str(dest),
                    file_type=FileType.UNKNOWN,
                    download_date=datetime.now(timezone.utc),
                )
                self._session.add(record)
                self._session.commit()

                result.downloaded += 1
                await emit(ProgressEvent("downloaded", f"Downloaded: {filename}", result.downloaded))

        await emit(ProgressEvent("done", f"Sync complete. Downloaded: {result.downloaded}, Skipped: {result.skipped}, Errors: {len(result.errors)}"))
        return result
