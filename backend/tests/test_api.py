"""
API endpoint tests using FastAPI TestClient.
Uses in-memory SQLite and mocked pipeline dependencies — no network, no LLM.
"""
import pytest
import json
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from app.api.deps import get_db, get_rag_pipeline
from app.models.base import Base
from app.models.file_record import DownloadedFile, FileType
from app.models.statement import ExtractedStatement
from app.rag.base import RAGResponse, Citation


# ---------------------------------------------------------------------------
# In-memory DB fixture wired into FastAPI
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def override_db(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def _get_test_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_test_db
    yield Session
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def seeded_db(override_db):
    """Insert a file + statement row for holdings/files tests."""
    Session = override_db
    with Session() as db:
        f = DownloadedFile(
            portal_file_id=1001,
            file_hash="aabbcc",
            portal_deal_id="10495",
            deal_name="Shared deal for home assignment",
            filename="fund_alpha_statement.pdf",
            file_path="/data/deal_10495/1001_fund_alpha_statement.pdf",
            file_type=FileType.CAPITAL_STATEMENT,
            classifier_confidence=0.95,
            download_date=datetime.now(timezone.utc),
        )
        db.add(f)
        db.flush()

        s = ExtractedStatement(
            file_id=f.id,
            fund_name="Fund Alpha LP",
            statement_date=date(2025, 9, 30),
            current_value=5_000_000.0,
        )
        db.add(s)
        db.commit()
    return override_db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def test_holdings_returns_latest_per_fund(client, seeded_db):
    r = client.get("/api/holdings")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["fund_name"] == "Fund Alpha LP"
    assert data[0]["current_value"] == pytest.approx(5_000_000.0)
    assert data[0]["statement_date"] == "2025-09-30"


def test_holdings_latest_wins(client, seeded_db):
    """When two statements exist for the same fund, only the latest is returned."""
    Session = seeded_db
    with Session() as db:
        # Re-fetch the file
        f = db.query(DownloadedFile).first()
        older = ExtractedStatement(
            file_id=f.id,
            fund_name="Fund Alpha LP",
            statement_date=date(2025, 3, 31),
            current_value=4_000_000.0,
        )
        db.add(older)
        db.commit()

    r = client.get("/api/holdings")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["current_value"] == pytest.approx(5_000_000.0)  # latest wins


def test_files_list(client, seeded_db):
    r = client.get("/api/files")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["filename"] == "fund_alpha_statement.pdf"
    assert data[0]["file_type"] == "capital_statement"


def test_chat_endpoint(client):
    """Chat endpoint returns answer + citations from the mocked RAG pipeline."""
    mock_rag = MagicMock()
    mock_rag.query = AsyncMock(return_value=RAGResponse(
        answer="The fund had strong performance in Q3 2025.",
        citations=[Citation(filename="report.pdf", file_path="/data/report.pdf", page=1, chunk_text="Strong performance...", period="Q3 2025")],
        is_out_of_corpus=False,
    ))
    app.dependency_overrides[get_rag_pipeline] = lambda: mock_rag

    r = client.post("/api/chat", json={"question": "How did the fund perform?"})
    assert r.status_code == 200
    data = r.json()
    assert "strong performance" in data["answer"].lower()
    assert len(data["citations"]) == 1
    assert data["is_out_of_corpus"] is False

    app.dependency_overrides.pop(get_rag_pipeline, None)
