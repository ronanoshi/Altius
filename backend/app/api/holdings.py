"""
GET /api/holdings  — latest statement per fund (the holdings table)
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.statement import ExtractedStatement

router = APIRouter(prefix="/api/holdings", tags=["holdings"])


@router.get("")
def get_holdings(db: Session = Depends(get_db)):
    """
    Returns one row per fund: the most recent statement by date.
    """
    # Subquery: max statement_date per fund
    latest = (
        db.query(
            ExtractedStatement.fund_name,
            func.max(ExtractedStatement.statement_date).label("max_date"),
        )
        .group_by(ExtractedStatement.fund_name)
        .subquery()
    )

    rows = (
        db.query(ExtractedStatement)
        .join(
            latest,
            (ExtractedStatement.fund_name == latest.c.fund_name)
            & (ExtractedStatement.statement_date == latest.c.max_date),
        )
        .all()
    )

    return [
        {
            "fund_name": r.fund_name,
            "current_value": r.current_value,
            "statement_date": r.statement_date.isoformat() if r.statement_date else None,
            "file_id": r.file_id,
        }
        for r in rows
    ]
