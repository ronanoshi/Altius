from datetime import datetime, date, timezone

from sqlalchemy import String, Float, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ExtractedStatement(Base):
    __tablename__ = "statements"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"), index=True)
    fund_name: Mapped[str] = mapped_column(String(512), index=True)
    statement_date: Mapped[date] = mapped_column(Date)
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_extracted_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    file: Mapped["DownloadedFile"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "DownloadedFile", backref="statements"
    )

    def __repr__(self) -> str:
        return (
            f"<ExtractedStatement id={self.id} fund={self.fund_name!r} "
            f"date={self.statement_date} value={self.current_value}>"
        )
