"""Tests that the DB schema and models work end-to-end using an in-memory SQLite DB."""
import pytest
from datetime import date, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.file_record import DownloadedFile, FileType
from app.models.statement import ExtractedStatement


@pytest.fixture(scope="module")
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    with Session() as s:
        yield s


def test_create_downloaded_file(session):
    """A DownloadedFile row can be inserted and queried back."""
    record = DownloadedFile(
        file_hash="abc123",
        portal_deal_id="deal-1",
        deal_name="Acme Growth Fund",
        filename="statement_q1_2024.pdf",
        file_path="/data/deal-1/statement_q1_2024.pdf",
        file_type=FileType.CAPITAL_STATEMENT,
        classifier_confidence=0.97,
        download_date=datetime(2024, 4, 1),
    )
    session.add(record)
    session.commit()

    fetched = session.query(DownloadedFile).filter_by(file_hash="abc123").one()
    assert fetched.deal_name == "Acme Growth Fund"
    assert fetched.file_type == FileType.CAPITAL_STATEMENT
    assert fetched.classifier_confidence == pytest.approx(0.97)


def test_create_extracted_statement(session):
    """An ExtractedStatement linked to a file can be inserted and queried back."""
    parent = session.query(DownloadedFile).filter_by(file_hash="abc123").one()

    stmt = ExtractedStatement(
        file_id=parent.id,
        fund_name="Acme Growth Fund",
        statement_date=date(2024, 3, 31),
        current_value=1_250_000.00,
        raw_extracted_json='{"ending_capital_balance": 1250000.00}',
    )
    session.add(stmt)
    session.commit()

    fetched = session.query(ExtractedStatement).filter_by(fund_name="Acme Growth Fund").one()
    assert fetched.current_value == pytest.approx(1_250_000.00)
    assert fetched.statement_date == date(2024, 3, 31)
    assert fetched.file_id == parent.id
