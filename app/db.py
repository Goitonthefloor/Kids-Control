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
    enroll_token = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    devices = relationship("Device", back_populates="child", cascade="all, delete-orphan")
    schedules = relationship("Schedule", back_populates="child", cascade="all, delete-orphan")
    app_rules = relationship("AppRule", back_populates="child", cascade="all, delete-orphan")
    watches = relationship("SoftwareWatch", back_populates="child", cascade="all, delete-orphan")


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
    ssh_enabled = Column(Boolean, nullable=False, default=False)
    ssh_host = Column(String, nullable=True)
    ssh_port = Column(Integer, nullable=False, default=22)
    ssh_user = Column(String, nullable=True)
    ssh_key_path = Column(String, nullable=True)
    ssh_host_pubkey = Column(String, nullable=True)
    setup_ticket = Column(String, unique=True, nullable=True)

    child = relationship("Child", back_populates="devices")
    software = relationship("SoftwareItem", back_populates="device", cascade="all, delete-orphan")
    commands = relationship("DeviceCommand", back_populates="device", cascade="all, delete-orphan")
    pending_updates = relationship("PendingUpdate", back_populates="device", cascade="all, delete-orphan")


class ServerSetting(Base):
    """Small key-value rows. The household install address is stored here."""

    __tablename__ = "server_settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)


class SetupEvent(Base):
    """One visible step while a child PC is being enrolled from the browser."""

    __tablename__ = "setup_events"

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String, nullable=False)
    detail = Column(String, nullable=True)
    at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


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
    remainder_seconds = Column(Integer, nullable=False, default=0)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("child_id", "day", name="uq_daily_usage_child_day"),
    )


class SoftwareWatch(Base):
    """Packages whose version should be tracked on the child's devices."""

    __tablename__ = "software_watches"

    id = Column(Integer, primary_key=True)
    child_id = Column(Integer, ForeignKey("children.id", ondelete="CASCADE"), nullable=False)
    package_name = Column(String, nullable=False)
    label = Column(String, nullable=False, default="")

    child = relationship("Child", back_populates="watches")

    __table_args__ = (
        UniqueConstraint("child_id", "package_name", name="uq_watch_child_package"),
    )


class SoftwareItem(Base):
    """Last reported version of a watched package on one device."""

    __tablename__ = "software_items"

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    package_name = Column(String, nullable=False)
    version = Column(String, nullable=False, default="")
    source = Column(String, nullable=False, default="unknown")
    reported_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    device = relationship("Device", back_populates="software")

    __table_args__ = (
        UniqueConstraint("device_id", "package_name", name="uq_software_device_package"),
    )


class PendingUpdate(Base):
    """Package upgrade reported by a Windows or Linux client."""

    __tablename__ = "pending_updates"

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    package_name = Column(String, nullable=False)
    installed_version = Column(String, nullable=False, default="")
    available_version = Column(String, nullable=False, default="")
    source = Column(String, nullable=False, default="unknown")
    reported_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    device = relationship("Device", back_populates="pending_updates")

    __table_args__ = (
        UniqueConstraint("device_id", "package_name", name="uq_pending_device_package"),
    )


class DeviceCommand(Base):
    """Queued remote action for an agent (or recorded SSH result)."""

    __tablename__ = "device_commands"

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String, nullable=False)  # update_one | update_all
    package_name = Column(String, nullable=True)
    status = Column(String, nullable=False, default="pending")  # pending|running|done|failed
    via = Column(String, nullable=False, default="agent")  # agent|ssh
    output = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    device = relationship("Device", back_populates="commands")


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
    _ensure_device_ssh_columns()
    _ensure_child_enroll_token()
    _ensure_usage_remainder()
    _ensure_command_started_at()
    _ensure_device_setup_ticket()
    _lock_down_data_files()


def _ensure_device_ssh_columns() -> None:
    """Add SSH columns on databases created before v1.1."""
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(devices)").fetchall()}
        alters = {
            "ssh_enabled": "BOOLEAN NOT NULL DEFAULT 0",
            "ssh_host": "VARCHAR",
            "ssh_port": "INTEGER NOT NULL DEFAULT 22",
            "ssh_user": "VARCHAR",
            "ssh_key_path": "VARCHAR",
            "ssh_host_pubkey": "VARCHAR",
        }
        for name, ddl in alters.items():
            if name not in cols:
                conn.exec_driver_sql(f"ALTER TABLE devices ADD COLUMN {name} {ddl}")


def _ensure_child_enroll_token() -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(children)").fetchall()}
        if "enroll_token" not in cols:
            conn.exec_driver_sql("ALTER TABLE children ADD COLUMN enroll_token VARCHAR")


def _ensure_usage_remainder() -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(daily_usage)").fetchall()}
        if "remainder_seconds" not in cols:
            conn.exec_driver_sql("ALTER TABLE daily_usage ADD COLUMN remainder_seconds INTEGER NOT NULL DEFAULT 0")


def _ensure_command_started_at() -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(device_commands)").fetchall()}
        if "started_at" not in cols:
            conn.exec_driver_sql("ALTER TABLE device_commands ADD COLUMN started_at DATETIME")


def _ensure_device_setup_ticket() -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(devices)").fetchall()}
        if "setup_ticket" not in cols:
            conn.exec_driver_sql("ALTER TABLE devices ADD COLUMN setup_ticket VARCHAR")


def _lock_down_data_files() -> None:
    import os

    from app.config import data_dir

    directory = data_dir()
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    for path in directory.iterdir():
        if path.is_file():
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass


def audit(db, *, actor: str, action: str, child_slug: str | None = None, details: str | None = None) -> None:
    db.add(
        AuditLog(
            actor=actor,
            child_slug=child_slug,
            action=action,
            details=details,
        )
    )
