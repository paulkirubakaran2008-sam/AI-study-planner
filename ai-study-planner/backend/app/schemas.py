from datetime import date, datetime

Date = date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .timeutil import hhmm

TIME = r"^([01]\d|2[0-3]):[0-5]\d$"
Window = Literal["morning", "afternoon", "evening", "night"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------ auth / user
class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    timezone: Optional[str] = Field(None, max_length=64)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class UserOut(ORM):
    id: int
    name: str
    email: str
    college: str
    department: str
    year: int
    is_demo: bool
    onboarded: bool = False
    theme: str = "light"


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class DemoIn(BaseModel):
    timezone: Optional[str] = Field(None, max_length=64)


# ------------------------------------------------------------------ settings
class PomodoroCfg(BaseModel):
    focus: int = Field(25, ge=5, le=90)
    short_break: int = Field(5, ge=1, le=30)
    long_break: int = Field(15, ge=5, le=60)
    rounds: int = Field(3, ge=1, le=8)


class SettingsOut(ORM):
    name: str
    college: str
    department: str
    year: int
    timezone: str
    daily_minutes: list[int]
    max_daily_minutes: int
    preferred_times: list[str]
    max_block_minutes: int
    break_minutes: int
    target_marks: int
    default_level: int
    blocked_dates: list[str]
    theme: str
    notifications_enabled: bool
    browser_notifications: bool
    pomodoro: PomodoroCfg


class SettingsIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    college: Optional[str] = Field(None, max_length=120)
    department: Optional[str] = Field(None, max_length=120)
    year: Optional[int] = Field(None, ge=1, le=8)
    timezone: Optional[str] = Field(None, max_length=64)
    daily_minutes: Optional[list[int]] = None
    max_daily_minutes: Optional[int] = Field(None, ge=30, le=600)
    preferred_times: Optional[list[Window]] = None
    max_block_minutes: Optional[int] = Field(None, ge=20, le=90)
    break_minutes: Optional[int] = Field(None, ge=5, le=30)
    target_marks: Optional[int] = Field(None, ge=40, le=100)
    blocked_dates: Optional[list[Date]] = None
    theme: Optional[Literal["light", "dark"]] = None
    notifications_enabled: Optional[bool] = None
    browser_notifications: Optional[bool] = None
    pomodoro: Optional[PomodoroCfg] = None

    @field_validator("daily_minutes")
    @classmethod
    def _seven(cls, v):
        if v is not None and (len(v) != 7 or any(x < 0 or x > 600 for x in v)):
            raise ValueError("daily_minutes needs 7 values between 0 and 600")
        return v


# ------------------------------------------------------------------ subjects / topics
class TopicIn(BaseModel):
    id: Optional[int] = None
    name: str = Field(min_length=1, max_length=120)
    difficulty: int = Field(3, ge=1, le=5)
    mastery: int = Field(40, ge=0, le=100)


class TopicOut(ORM):
    id: int
    subject_id: int
    name: str
    difficulty: int
    mastery: int
    last_confidence: Optional[int]
    last_studied: Optional[date]
    review_stage: int
    miss_count: int


class SubjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    difficulty: int = Field(3, ge=1, le=5)
    importance: int = Field(3, ge=1, le=5)
    target_marks: int = Field(80, ge=40, le=100)
    exam_date: Optional[Date] = None
    topics: list[TopicIn] = Field(default_factory=list, max_length=60)


class SubjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    difficulty: Optional[int] = Field(None, ge=1, le=5)
    importance: Optional[int] = Field(None, ge=1, le=5)
    target_marks: Optional[int] = Field(None, ge=40, le=100)
    exam_date: Optional[Date] = None
    clear_exam: bool = False


class SubjectOut(BaseModel):
    id: int
    name: str
    color: str
    difficulty: int
    importance: int
    target_marks: int
    exam_date: Optional[Date]
    days_left: Optional[int]
    preparation: int
    topics: list[TopicOut]


class TopicUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    difficulty: Optional[int] = Field(None, ge=1, le=5)
    mastery: Optional[int] = Field(None, ge=0, le=100)


# ------------------------------------------------------------------ onboarding
class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    college: str = Field("", max_length=120)
    department: str = Field("", max_length=120)
    year: int = Field(1, ge=1, le=8)


class OnboardingIn(BaseModel):
    profile: ProfileIn
    subjects: list[SubjectIn] = Field(min_length=1, max_length=15)
    weekday_minutes: int = Field(180, ge=0, le=600)
    weekend_minutes: int = Field(240, ge=0, le=600)
    preferred_times: list[Window] = Field(default_factory=lambda: ["morning", "evening"])
    default_level: int = Field(40, ge=0, le=100)
    target_marks: int = Field(80, ge=40, le=100)
    timezone: Optional[str] = Field(None, max_length=64)


# ------------------------------------------------------------------ tasks
Status = Literal["pending", "in_progress", "completed", "skipped", "overdue"]
Level = Literal["critical", "high", "medium", "low"]


class TaskOut(BaseModel):
    id: int
    subject_id: int
    subject_name: str
    subject_color: str
    topic_id: Optional[int]
    topic_name: Optional[str]
    title: str
    task_type: str
    date: Date
    start_time: str
    end_time: str
    start_minute: int
    duration_minutes: int
    priority: str
    priority_score: float
    difficulty: int
    status: str
    notes: str
    origin: str
    locked: bool
    moved_from: Optional[date]
    reschedule_count: int
    reason: str
    actual_minutes: int
    confidence: Optional[int]


def task_out(t) -> TaskOut:
    return TaskOut(id=t.id, subject_id=t.subject_id, subject_name=t.subject.name, subject_color=t.subject.color,
                   topic_id=t.topic_id, topic_name=t.topic.name if t.topic else None, title=t.title, task_type=t.task_type,
                   date=t.date, start_time=hhmm(t.start_minute), end_time=hhmm(t.start_minute + t.duration_minutes),
                   start_minute=t.start_minute, duration_minutes=t.duration_minutes, priority=t.priority,
                   priority_score=t.priority_score, difficulty=t.difficulty, status=t.status, notes=t.notes, origin=t.origin,
                   locked=t.locked, moved_from=t.moved_from, reschedule_count=t.reschedule_count, reason=t.reason,
                   actual_minutes=t.actual_minutes, confidence=t.confidence)


class TaskIn(BaseModel):
    subject_id: int
    topic_id: Optional[int] = None
    title: Optional[str] = Field(None, max_length=160)
    date: Date
    start_time: str = Field(pattern=TIME)
    duration_minutes: int = Field(45, ge=5, le=240)
    priority: Optional[Level] = None
    difficulty: Optional[int] = Field(None, ge=1, le=5)
    task_type: Literal["study", "revision", "practice"] = "study"
    notes: str = Field("", max_length=500)


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=160)
    date: Optional[Date] = None
    start_time: Optional[str] = Field(None, pattern=TIME)
    duration_minutes: Optional[int] = Field(None, ge=5, le=240)
    priority: Optional[Level] = None
    status: Optional[Status] = None
    notes: Optional[str] = Field(None, max_length=500)


class CompleteIn(BaseModel):
    confidence: Optional[int] = Field(None, ge=1, le=5)
    actual_minutes: Optional[int] = Field(None, ge=0, le=600)


class SkipIn(BaseModel):
    reschedule: bool = True


class SessionIn(BaseModel):
    task_id: Optional[int] = None
    subject_id: Optional[int] = None
    topic_id: Optional[int] = None
    duration_minutes: int = Field(ge=1, le=300)
    planned_minutes: int = Field(0, ge=0, le=300)
    mode: Literal["focus", "pomodoro"] = "focus"
    confidence: Optional[int] = Field(None, ge=1, le=5)
    complete_task: bool = False


class RebalanceIn(BaseModel):
    date: Date


# ------------------------------------------------------------------ recommendations / assistant / notifications
class RecommendationOut(ORM):
    id: int
    kind: str
    title: str
    body: str
    reason: str
    severity: str
    source: str
    ai_explanation: Optional[str]
    action: Optional[dict]
    status: str
    created_at: datetime


class AssistantIn(BaseModel):
    text: str = Field(min_length=2, max_length=400)


class AssistantApplyIn(BaseModel):
    actions: list[dict] = Field(min_length=1, max_length=8)


class NotificationOut(ORM):
    id: int
    kind: str
    title: str
    body: str
    read: bool
    created_at: datetime
