"""Demo mode: every demo visitor gets their *own throw-away user* (is_demo=True) with realistic sample data.
Demo rows are never shared with real accounts and are purged after DEMO_TTL_HOURS."""
import random
import secrets
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from .. import models as m
from ..config import get_settings
from ..security import hash_password
from ..timeutil import local_now
from . import analytics_service as analytics
from . import planner_service as planner

COLORS = ["#3B5BDB", "#E8590C", "#0CA678", "#AE3EC9", "#F08C00", "#1098AD"]

SAMPLE = [
    ("Data Structures", 4, 5, 12, [("Arrays", 2, 90), ("Linked Lists", 3, 70), ("Stacks", 3, 60), ("Queues", 3, 45), ("Trees", 4, 30), ("Graphs", 5, 20)]),
    ("Operating Systems", 4, 4, 16, [("Process Scheduling", 3, 65), ("Deadlocks", 4, 50), ("Virtual Memory", 5, 35), ("File Systems", 3, 55)]),
    ("Python", 2, 3, 21, [("Data Types", 1, 90), ("Functions & OOP", 3, 70), ("File Handling", 2, 60), ("Practice Problems", 3, 50)]),
    ("Java", 3, 3, 26, [("OOP Concepts", 3, 60), ("Collections", 3, 40), ("Exceptions", 2, 55), ("Multithreading", 4, 25)]),
]


def purge_old_demos(db: Session) -> None:
    cutoff = datetime.utcnow() - timedelta(hours=get_settings().demo_ttl_hours)
    for u in db.query(m.User).filter(m.User.is_demo.is_(True), m.User.created_at < cutoff).all():
        db.delete(u)
    db.commit()


def create_demo_user(db: Session, tz: str | None = None) -> m.User:
    purge_old_demos(db)
    tz = tz or "Asia/Kolkata"
    user = m.User(email=f"demo-{secrets.token_hex(6)}@demo.example.com", name="Sam", password_hash=hash_password(secrets.token_urlsafe(16)),
                  college="Rathinam Technical Campus", department="Computer Science & Engineering", year=2, is_demo=True)
    user.preferences = m.StudyPreferences(timezone=tz, daily_minutes=[180, 180, 180, 180, 180, 240, 240], max_daily_minutes=300,
                                          preferred_times=["morning", "evening"], target_marks=85, onboarded=True)
    db.add(user)
    db.flush()
    now = local_now(tz)
    today = now.date()
    topics: list[m.Topic] = []
    subjects: list[m.Subject] = []
    for i, (name, diff, imp, days, tps) in enumerate(SAMPLE):
        s = m.Subject(user_id=user.id, name=name, color=COLORS[i], difficulty=diff, importance=imp, target_marks=85)
        db.add(s)
        db.flush()
        db.add(m.Exam(user_id=user.id, subject_id=s.id, title="End semester", exam_date=today + timedelta(days=days)))
        for j, (tn, td, mastery) in enumerate(tps):
            t = m.Topic(subject_id=s.id, name=tn, difficulty=td, mastery=mastery, position=j, last_studied=today - timedelta(days=j % 4 + 1))
            db.add(t)
            topics.append(t)
        subjects.append(s)
    db.flush()

    # ten days of believable history so streak/analytics show real numbers: a 7-day streak ending yesterday
    rng = random.Random(42)
    studied_offsets = [1, 2, 3, 4, 5, 6, 7, 9, 10, 11]
    for off in range(1, 12):
        day = today - timedelta(days=off)
        n = rng.choice([2, 3, 3])
        picks = rng.sample(topics, n)
        start = 9 * 60
        for k, tp in enumerate(picks):
            dur = rng.choice([40, 45, 50])
            studied = off in studied_offsets and not (off == 4 and k == 2) and not (off == 9 and k == 1)
            task = m.StudyTask(user_id=user.id, subject_id=tp.subject_id, topic_id=tp.id, title=tp.name, date=day,
                               start_minute=start + k * 120 if k < 2 else 18 * 60, duration_minutes=dur,
                               priority=rng.choice(["high", "medium", "medium", "low"]), priority_score=0.4, difficulty=tp.difficulty,
                               status="completed" if studied else ("skipped" if off in studied_offsets else "overdue"),
                               origin="generated", handled=True, reason="Sample history")
            if studied:
                task.actual_minutes = dur - rng.choice([0, 0, 5])
                task.confidence = rng.choice([3, 3, 4, 4, 5])
                task.completed_at = datetime.utcnow() - timedelta(days=off)
            db.add(task)
            db.flush()
            if studied and k < 2:
                db.add(m.StudySession(user_id=user.id, task_id=task.id, subject_id=tp.subject_id, topic_id=tp.id, local_date=day,
                                      duration_minutes=task.actual_minutes, planned_minutes=dur, mode="focus",
                                      confidence=task.confidence, started_at=datetime.utcnow() - timedelta(days=off)))
    db.flush()
    for off in range(0, 12):
        analytics.refresh_day(db, user, today - timedelta(days=off))
    db.refresh(user)
    planner.generate(db, user, now)
    analytics.refresh_day(db, user, today)
    db.commit()
    return user
