"""In-app notification generation (deduplicated by key). The frontend also mirrors new ones as browser notifications
when the student has granted permission. Everything here is plain logic - no AI."""
from datetime import date, datetime, timedelta

from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from .. import models as m
from ..timeutil import hhmm, local_now
from . import planner_service as planner
from . import streak_service


def _add(db: Session, user: m.User, existing: set[str], kind: str, key: str, title: str, body: str = "") -> None:
    if key in existing:
        return
    existing.add(key)
    ins = (postgresql.insert if db.get_bind().dialect.name == "postgresql" else sqlite.insert)(m.Notification).values(
        user_id=user.id, kind=kind, dedupe_key=key, title=title, body=body, read=False, created_at=datetime.utcnow())
    # concurrent requests (e.g. dashboard + notifications) may race on the same key: the unique constraint wins silently
    db.execute(ins.on_conflict_do_nothing(index_elements=["user_id", "dedupe_key"]))


def generate(db: Session, user: m.User, now: datetime | None = None) -> None:
    prefs = user.preferences
    if not prefs.notifications_enabled:
        return
    now = now or local_now(prefs.timezone)
    today, minute = now.date(), now.hour * 60 + now.minute
    since = datetime.utcnow() - timedelta(days=4)
    existing = {k for (k,) in db.query(m.Notification.dedupe_key).filter(m.Notification.user_id == user.id,
                                                                          m.Notification.created_at > since)}

    todays = (db.query(m.StudyTask).filter(m.StudyTask.user_id == user.id, m.StudyTask.date == today,
                                           m.StudyTask.status.in_(("pending", "in_progress"))).order_by(m.StudyTask.start_minute).all())
    if todays and minute >= 6 * 60:
        total = sum(t.duration_minutes for t in todays)
        _add(db, user, existing, "daily_plan", f"daily:{today}", "Today's plan is ready",
             f"{len(todays)} session(s), {total // 60}h {total % 60}m. First up: {todays[0].title} at {hhmm(todays[0].start_minute)}.")
    for t in todays:
        if t.status == "pending" and 0 <= t.start_minute - minute <= 15:
            _add(db, user, existing, "upcoming_session", f"upcoming:{t.id}", f"Starting soon: {t.title}",
                 f"{t.subject.name} · {t.duration_minutes} min at {hhmm(t.start_minute)}")

    missed = (db.query(m.StudyTask).filter(m.StudyTask.user_id == user.id, m.StudyTask.status.in_(("overdue", "skipped")),
                                           m.StudyTask.date >= today - timedelta(days=1)).all())
    for t in missed:
        _add(db, user, existing, "missed_task", f"missed:{t.id}", f"Missed: {t.title}",
             f"{t.subject.name} on {t.date:%a %d %b}. I've rebuilt the rest of your plan around it.")

    for s in user.subjects:
        exam = planner.subject_exam(s, today)
        if exam:
            days = (exam - today).days
            for th in (7, 3, 1):
                if days <= th and days >= 0:
                    _add(db, user, existing, "exam_approaching", f"exam:{s.id}:{exam}:{th}", f"{s.name} exam in {days} day(s)",
                         "Check your plan and prioritise weak topics.")
                    break

    st = streak_service.summary(db, user.id, today)
    if st["current"] >= 1 and not st["studied_today"] and minute >= 18 * 60:
        _add(db, user, existing, "streak_reminder", f"streak:{today}", f"Keep your {st['current']}-day streak",
             "Log 10 minutes today to keep it going.")
    db.flush()
