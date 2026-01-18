from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker

DB_PATH = "/opt/kids-control/app/data/kidscontrol.sqlite3"
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()

class Child(Base):
    __tablename__ = "children"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)  # z.B. "kind1"
    display_name = Column(String, nullable=False)           # z.B. "Kind 1"

class Schedule(Base):
    """
    Ein Zeitfenster pro Wochentag und Kind.
    weekday: 0=Mo ... 6=So
    start_min/end_min: Minuten ab 00:00 (z.B. 15:00 => 900)
    daily_minutes: erlaubte Minuten am Tag
    """
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False)
    weekday = Column(Integer, nullable=False)
    start_min = Column(Integer, nullable=False, default=900)   # 15:00
    end_min = Column(Integer, nullable=False, default=1110)    # 18:30
    daily_minutes = Column(Integer, nullable=False, default=120)

    __table_args__ = (UniqueConstraint("username", "weekday", name="uq_schedule_user_weekday"),)

class ChildPolicy(Base):
    __tablename__ = "child_policy"

    username = Column(String, primary_key=True)
    after_expiry_mode = Column(String, nullable=False, default="LOCK")  # LOCK|SCHOOL
    hard_lock = Column(Boolean, nullable=False, default=True)
    warn_minutes = Column(Integer, nullable=False, default=10)  # Vorwarnzeit


class PrewarnLog(Base):
    __tablename__ = "prewarn_log"

    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False)
    day = Column(String, nullable=False)  # YYYY-MM-DD
    mode = Column(String, nullable=False)  # LOCK|SCHOOL
    shown_at = Column(String, nullable=False)  # ISO timestamp

    __table_args__ = (
        UniqueConstraint("username", "day", "mode", name="uq_prewarn_user_day_mode"),
    )

class Override(Base):
    __tablename__ = "overrides"
    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False)
    grant_until = Column(DateTime(timezone=True), nullable=False)
    grant_type = Column(String, nullable=False)  # HOUR | DAY
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    actor = Column(String, nullable=False)       # Eltern-User
    child = Column(String, nullable=True)        # betroffener Kind-User (optional)
    action = Column(String, nullable=False)      # z.B. SCHEDULE_UPDATE, GRANT_DAY_ON
    details = Column(String, nullable=True)      # Freitext (kurz)

class DailyUsage(Base):
    __tablename__ = "daily_usage"

    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False)
    day = Column(String, nullable=False)  # YYYY-MM-DD (lokaler Tag!)
    used_minutes = Column(Integer, nullable=False, default=0)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("username", "day", name="uq_daily_usage_user_day"),
    )
class DayOverride(Base):
    __tablename__ = "day_overrides"
    username = Column(String, primary_key=True)
    day = Column(String, nullable=False)  # YYYY-MM-DD (lokales Datum)
    enabled = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

def init_db():
    Base.metadata.create_all(bind=engine)
