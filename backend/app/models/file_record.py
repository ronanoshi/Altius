import enum
from datetime import datetime, timezone

from sqlalchemy import String, Float, DateTime, Integer, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class FileType(str, enum.Enum):
    CAPITAL_STATEMENT = "capital_statement"
    REPORT = "report"
    OTHER = "other"
    UNKNOWN = "unknown"


class DownloadedFile(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    portal_file_id: Mapped[int | None] = mapped_column(Integer, unique=True, index=True, nullable=True)
    file_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    portal_deal_id: Mapped[str] = mapped_column(String(256))
    deal_name: Mapped[str] = mapped_column(String(512))
    filename: Mapped[str] = mapped_column(String(512))
    file_path: Mapped[str] = mapped_column(String(1024))
    file_type: Mapped[FileType] = mapped_column(
        SAEnum(FileType), default=FileType.UNKNOWN
    )
    classifier_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    download_date: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return (
            f"<DownloadedFile id={self.id} filename={self.filename!r} "
            f"type={self.file_type}>"
        )
