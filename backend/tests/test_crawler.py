"""
Crawler tests.

Unit tests mock all external calls and verify idempotency logic.
The integration test runs the actual sync against the live portal.
"""
import pytest
import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.file_record import DownloadedFile, FileType
from app.crawler.base import SyncResult, ProgressEvent
from app.crawler.httpx_crawler import HttpxCrawler
from app.config import Settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    with Session() as s:
        yield s


@pytest.fixture
def fake_settings(tmp_path):
    s = MagicMock(spec=Settings)
    s.portal_url = "https://fo1.altius.finance"
    s.portal_username = "user@test.com"
    s.portal_password = "password"
    s.data_dir = str(tmp_path)
    return s


def _make_portal_client(files: list[dict]):
    client = MagicMock()
    client.login = AsyncMock(return_value="fake-token")
    client.list_deals = AsyncMock(return_value=[{"id": 1, "title": "Test Deal"}])
    client.list_files = AsyncMock(return_value=files)

    async def fake_download(url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"%PDF fake content for " + url.encode()[:20])

    client.download_file = AsyncMock(side_effect=fake_download)
    return client


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_downloads_new_files(db_session, fake_settings):
    """New files are downloaded and recorded in the DB."""
    files = [
        {"id": 101, "name": "report_q1.pdf", "file_url": "https://s3/file101.pdf", "section_id": 1},
        {"id": 102, "name": "statement.pdf", "file_url": "https://s3/file102.pdf", "section_id": 1},
    ]
    client = _make_portal_client(files)
    crawler = HttpxCrawler(fake_settings, db_session, client=client)

    result = await crawler.sync()

    assert result.downloaded == 2
    assert result.skipped == 0
    assert result.errors == []
    assert db_session.query(DownloadedFile).filter_by(portal_file_id=101).one() is not None
    assert db_session.query(DownloadedFile).filter_by(portal_file_id=102).one() is not None


@pytest.mark.asyncio
async def test_sync_is_idempotent(db_session, fake_settings):
    """Re-running sync skips files already in the DB — no duplicates, no re-downloads."""
    files = [
        {"id": 101, "name": "report_q1.pdf", "file_url": "https://s3/file101.pdf", "section_id": 1},
        {"id": 102, "name": "statement.pdf", "file_url": "https://s3/file102.pdf", "section_id": 1},
    ]
    client = _make_portal_client(files)
    crawler = HttpxCrawler(fake_settings, db_session, client=client)

    result = await crawler.sync()

    assert result.downloaded == 0
    assert result.skipped == 2
    # download_file should NOT have been called again
    client.download_file.assert_not_called()


# ---------------------------------------------------------------------------
# Integration test — runs against the live portal
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_sync(tmp_path):
    """
    Runs a full sync against fo1.altius.finance.
    Expects at least 40 files in deal 10495 (folder '1').
    Flags any files from investor 'error2' for manual review.
    """
    from app.database import init_db, SessionLocal
    from app.crawler import HttpxCrawler
    from app.config import settings

    # Use a fresh on-disk DB in tmp_path so this test is self-contained
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    events: list[ProgressEvent] = []

    async def capture(event: ProgressEvent):
        events.append(event)
        print(f"  [{event.type}] {event.message}")

    live_settings = MagicMock(spec=Settings)
    live_settings.portal_url = settings.portal_url
    live_settings.portal_username = settings.portal_username
    live_settings.portal_password = settings.portal_password
    live_settings.data_dir = str(tmp_path / "data")

    with Session() as session:
        crawler = HttpxCrawler(live_settings, session)
        result = await crawler.sync(progress=capture)

    print(f"\nResult: downloaded={result.downloaded} skipped={result.skipped} errors={len(result.errors)}")
    for err in result.errors:
        print(f"  ERROR: {err}")

    # Verify we got all expected files
    assert result.downloaded >= 40, f"Expected >=40 files, got {result.downloaded}"
    assert result.errors == [] or all("error2" in e.lower() for e in result.errors), \
        f"Unexpected errors: {result.errors}"

    # Re-run: everything should be skipped (idempotency)
    with Session() as session:
        crawler2 = HttpxCrawler(live_settings, session)
        result2 = await crawler2.sync()

    assert result2.downloaded == 0
    assert result2.skipped == result.downloaded
