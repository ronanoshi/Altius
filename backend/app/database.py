from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Generator

from .config import settings
from .models.base import Base

# Import models so Base.metadata knows about them
from .models import DownloadedFile, ExtractedStatement  # noqa: F401

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},  # SQLite only
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
