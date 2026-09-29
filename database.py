"""
database.py
───────────
Async SQLAlchemy 2.0 engine, session factory, and ORM models.

Tables
------
  events    – append-only log of every camera event received
  occupants – current state of every person/intruder in the system
              (upserted on each event so the server can replay state
               to a freshly-connected WebSocket client)
"""

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import (
    Boolean, DateTime, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

load_dotenv()

DATABASE_URL: str = os.environ["DATABASE_URL"]

# ── Engine ────────────────────────────────────────────────────────────────────
engine = create_async_engine(
    DATABASE_URL,
    echo=False,          # set True to log SQL during development
    pool_pre_ping=True,  # drop stale connections automatically
    pool_size=5,
    max_overflow=10,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Base ──────────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Models ────────────────────────────────────────────────────────────────────

class Event(Base):
    """
    Append-only forensic log.
    Every POST to /api/event writes one row here regardless of occupant state.
    """
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(String(32), nullable=False)   # entry | visitor | hotzone | safe
    msg: Mapped[str] = mapped_column(Text, nullable=False)
    camera: Mapped[str] = mapped_column(String(64), nullable=False)
    zone: Mapped[str] = mapped_column(String(128), nullable=False)
    floor: Mapped[int] = mapped_column(Integer, nullable=False)
    is_hotzone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Denormalised occupant snapshot at event time (nullable – not every
    # event carries occupant data)
    occupant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occupant_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    occupant_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occupant_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occupant_avatar: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # Which camera node posted this event (from JWT sub claim)
    posted_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Occupant(Base):
    """
    Current state of each person / intruder.
    Rows are upserted (INSERT … ON CONFLICT DO UPDATE) so this table always
    reflects the latest known position of each occupant.
    """
    __tablename__ = "occupants"
    __table_args__ = (
        UniqueConstraint("occupant_id", name="uq_occupants_occupant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occupant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)    # REGISTERED | VISITOR_LOBBY | UNREGISTERED_HOTZONE
    role: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)  # MISSING | SAFE | VISITOR_ALLOWED | HOTZONE_BREACH
    floor: Mapped[int] = mapped_column(Integer, nullable=False)
    zone: Mapped[str] = mapped_column(String(128), nullable=False)
    is_hotzone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    camera: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_time: Mapped[str] = mapped_column(String(32), nullable=False)
    avatar: Mapped[str] = mapped_column(String(8), nullable=False, default="👤")
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

async def create_tables() -> None:
    """Create all tables if they don't exist. Called once at startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    """FastAPI dependency – yields a session and guarantees cleanup."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
