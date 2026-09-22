"""SQLAlchemy models and database bootstrap."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from app.config import database_url

engine = create_engine(
    database_url(),
    connect_args={"check_same_thread": False} if database_url().startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Child(Base):
    __tablename__ = "children"

    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, nullable=False)  # stable id e.g. "mia"
    display_name = Column(String, nullable=False)
    timezone = Column(String, nullable=False, default="Europe/Berlin")
    active = Column(Boolean, nullable=False, default=True)
    warn_minutes = Column(Integer, nullable=False, default=10)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    devices = relationship("Device", back_populates="child", cascade="all, delete-orphan")
    schedules = relationship("Schedule", back_populates="child", cascade="all, delete-orphan")
    app_rules = relationship("AppRule", back_populates="child", cascade="all, delete-orphan")


class Device(Base):
    """A PC/laptop running the KidsControl agent for one child."""

    __tablename__ = "devices"

    id = Column(Integer, primary_key=True)
    child_id = Column(Integer, ForeignKey("children.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    device_key = Column(String, unique=True, nullable=False)
    os_family = Column(String, nullable=False, default="unknown")  # linux|windows|macos|unknown
    hostname = Column(String, nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    child = relationship("Child", back_populates="devices")


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True)
    child_id = Column(Integer, ForeignKey("children.id", ondelete="CASCADE"), nullable=False)
    weekday = Column(Integer, nullable=False)  # 0=Mon ... 6=Sun
    start_min = Column(Integer, nullable=False, default=900)
    end_min = Column(Integer, nullable=False, default=1110)
    daily_minutes = Column(Integer, nullable=False, default=120)

    child = relationship("Child", back_populates="schedules")

    __table_args__ = (
        UniqueConstraint("child_id", "weekday", name="uq_schedule_child_weekday"),
    )


class AppRule(Base):
    """Block apps by process/executable name pattern (OS-independent matching)."""

    __tablename__ = "app_rules"

    id = Column(Integer, primary_key=True)
    child_id = Column(Integer, ForeignKey("children.id", ondelete="CASCADE"), nullable=False)
    label = Column(String, nullable=False, default="")
    pattern = Column(String, nullable=False)  # e.g. minecraft, RobloxPlayerBeta.exe
    match_mode = Column(String, nullable=False, default="contains")  # contains|exact|startswith
    enabled = Column(Boolean, nullable=False, default=True)
    # always: block even during allowed screen time
    # when_denied: only relevant when session already denied (agent still reports)
    scope = Column(String, nullable=False, default="always")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    child = relationship("Child", back_populates="app_rules")


class Override(Base):
    __tablename__ = "overrides"

    id = Column(Integer, primary_key=True)
    child_id = Column(Integer, ForeignKey("children.id", ondelete="CASCADE"), nullable=False)
    grant_until = Column(DateTime(timezone=True), nullable=False)
    grant_type = Column(String, nullable=False)  # HOUR | DAY
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class DayOverride(Base):
    __tablename__ = "day_overrides"

    id = Column(Integer, primary_key=True)
    child_id = Column(Integer, ForeignKey("children.id", ondelete="CASCADE"), nullable=False)
    day = Column(String, nullable=False)  # YYYY-MM-DD local
    enabled = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("child_id", "day", name="uq_day_override_child_day"),
    )


class DailyUsage(Base):
    __tablename__ = "daily_usage"

    id = Column(Integer, primary_key=True)
    child_id = Column(Integer, ForeignKey("children.id", ondelete="CASCADE"), nullable=False)
    day = Column(String, nullable=False)
    used_minutes = Column(Integer, nullable=False, default=0)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("child_id", "day", name="uq_daily_usage_child_day"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    actor = Column(String, nullable=False)
    child_slug = Column(String, nullable=True)
    action = Column(String, nullable=False)
    details = Column(String, nullable=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def audit(db, *, actor: str, action: str, child_slug: str | None = None, details: str | None = None) -> None:
    db.add(
        AuditLog(
            actor=actor,
            child_slug=child_slug,
            action=action,
            details=details,
        )
    )
