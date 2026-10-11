"""SQLAlchemy models. Dates are the *user's local calendar dates*; clock times are minutes from midnight."""
from datetime import date, datetime, timezone

from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(100))
    college: Mapped[str] = mapped_column(String(120), default="")
    department: Mapped[str] = mapped_column(String(120), default="")
    year: Mapped[int] = mapped_column(Integer, default=1)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    preferences: Mapped["StudyPreferences"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    subjects: Mapped[list["Subject"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class StudyPreferences(Base):
    __tablename__ = "study_preferences"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    # study minutes available per weekday, Monday=0 ... Sunday=6
    daily_minutes: Mapped[list] = mapped_column(JSON, default=lambda: [180, 180, 180, 180, 180, 240, 240])
    max_daily_minutes: Mapped[int] = mapped_column(Integer, default=300)
    preferred_times: Mapped[list] = mapped_column(JSON, default=lambda: ["morning", "evening"])
    max_block_minutes: Mapped[int] = mapped_column(Integer, default=50)
    break_minutes: Mapped[int] = mapped_column(Integer, default=10)
    sleep_start: Mapped[int] = mapped_column(Integer, default=23 * 60)   # no study after this
    wake_time: Mapped[int] = mapped_column(Integer, default=6 * 60)
    target_marks: Mapped[int] = mapped_column(Integer, default=80)
    default_level: Mapped[int] = mapped_column(Integer, default=40)       # starting mastery %
    blocked_dates: Mapped[list] = mapped_column(JSON, default=list)       # ISO dates the student cannot study
    day_overrides: Mapped[dict] = mapped_column(JSON, default=dict)       # {"2026-10-12": 90} minutes for one day
    focus_boosts: Mapped[dict] = mapped_column(JSON, default=dict)        # {"<subject_id>": "2026-10-15"} focus until date
    theme: Mapped[str] = mapped_column(String(10), default="light")
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    browser_notifications: Mapped[bool] = mapped_column(Boolean, default=False)
    pomodoro: Mapped[dict] = mapped_column(JSON, default=lambda: {"focus": 25, "short_break": 5, "long_break": 15, "rounds": 3})
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False)
    last_planned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user: Mapped[User] = relationship(back_populates="preferences")


class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    color: Mapped[str] = mapped_column(String(9), default="#3D5AFE")
    difficulty: Mapped[int] = mapped_column(Integer, default=3)     # 1..5
    importance: Mapped[int] = mapped_column(Integer, default=3)     # 1..5 (credit weight / personal priority)
    target_marks: Mapped[int] = mapped_column(Integer, default=80)  # 0..100
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    user: Mapped[User] = relationship(back_populates="subjects")
    topics: Mapped[list["Topic"]] = relationship(back_populates="subject", cascade="all, delete-orphan", order_by="Topic.position")
    exams: Mapped[list["Exam"]] = relationship(back_populates="subject", cascade="all, delete-orphan", order_by="Exam.exam_date")
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_subject_user_name"),)


class Exam(Base):
    __tablename__ = "exams"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120), default="Final exam")
    exam_date: Mapped[date] = mapped_column(Date)
    start_minute: Mapped[int] = mapped_column(Integer, default=10 * 60)
    subject: Mapped[Subject] = relationship(back_populates="exams")


class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    difficulty: Mapped[int] = mapped_column(Integer, default=3)
    mastery: Mapped[int] = mapped_column(Integer, default=40)       # 0..100
    position: Mapped[int] = mapped_column(Integer, default=0)
    last_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_studied: Mapped[date | None] = mapped_column(Date, nullable=True)
    review_stage: Mapped[int] = mapped_column(Integer, default=0)
    miss_count: Mapped[int] = mapped_column(Integer, default=0)     # sessions missed/skipped (feeds priority)
    subject: Mapped[Subject] = relationship(back_populates="topics")


class StudyTask(Base):
    __tablename__ = "study_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(160), default="")
    task_type: Mapped[str] = mapped_column(String(12), default="study")   # study | revision | practice
    date: Mapped[date] = mapped_column(Date)
    start_minute: Mapped[int] = mapped_column(Integer)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    priority: Mapped[str] = mapped_column(String(10), default="medium")   # critical | high | medium | low
    priority_score: Mapped[float] = mapped_column(Float, default=0.0)
    difficulty: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(String(12), default="pending")    # pending|in_progress|completed|skipped|overdue
    notes: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(String(12), default="generated")  # generated | manual | assistant | spaced
    locked: Mapped[bool] = mapped_column(Boolean, default=False)           # hand-placed -> replans never delete it
    handled: Mapped[bool] = mapped_column(Boolean, default=False)          # missed task already rescheduled
    moved_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    reschedule_count: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(String(240), default="")           # short "why scheduled" explanation
    actual_minutes: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    subject: Mapped[Subject] = relationship()
    topic: Mapped[Topic | None] = relationship()
    __table_args__ = (Index("ix_tasks_user_date", "user_id", "date"), Index("ix_tasks_user_status", "user_id", "status"))


class StudySession(Base):
    __tablename__ = "study_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    task_id: Mapped[int | None] = mapped_column(ForeignKey("study_tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"), nullable=True)
    local_date: Mapped[date] = mapped_column(Date)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=0)
    planned_minutes: Mapped[int] = mapped_column(Integer, default=0)
    mode: Mapped[str] = mapped_column(String(12), default="focus")        # focus | pomodoro
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    __table_args__ = (Index("ix_sessions_user_date", "user_id", "local_date"),)


class Progress(Base):
    """One row per user per day: the persisted daily rollup used by analytics and streaks."""
    __tablename__ = "progress"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    day: Mapped[date] = mapped_column(Date)
    planned_minutes: Mapped[int] = mapped_column(Integer, default=0)
    actual_minutes: Mapped[int] = mapped_column(Integer, default=0)
    tasks_planned: Mapped[int] = mapped_column(Integer, default=0)
    tasks_completed: Mapped[int] = mapped_column(Integer, default=0)
    tasks_missed: Mapped[int] = mapped_column(Integer, default=0)
    focus_sessions: Mapped[int] = mapped_column(Integer, default=0)
    study_score: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_progress_user_day"), Index("ix_progress_user_day", "user_id", "day"))


class AIRecommendation(Base):
    __tablename__ = "ai_recommendations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, default="")
    action: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    severity: Mapped[str] = mapped_column(String(10), default="info")      # info | warn | urgent
    source: Mapped[str] = mapped_column(String(10), default="rules")       # rules | ai
    ai_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(10), default="active")      # active | applied | dismissed | stale
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (Index("ix_reco_user_key", "user_id", "dedupe_key"),)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))   # upcoming_session | missed_task | exam_approaching | daily_plan | streak_reminder
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text, default="")
    dedupe_key: Mapped[str] = mapped_column(String(120))
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "dedupe_key", name="uq_notif_dedupe"), Index("ix_notif_user_read", "user_id", "read"))


class AICache(Base):
    """Cache for AI responses keyed by a hash of the (small) prompt, so identical requests never re-bill."""
    __tablename__ = "ai_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    response: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AIUsage(Base):
    __tablename__ = "ai_usage"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    day: Mapped[date] = mapped_column(Date)
    calls: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_aiusage_user_day"),)
