"""Database connection and session management for SQLModel."""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlmodel import SQLModel

from src.common.core.config import get_settings

settings = get_settings()

# Base class for SQLModel - used by Alembic for migrations
Base = SQLModel

engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Initialize database tables."""
    SQLModel.metadata.create_all(bind=engine)


def get_session() -> Generator[Session, None, None]:
    """Dependency for getting database session."""
    with SessionLocal() as session:
        try:
            yield session
        finally:
            session.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager for database session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()