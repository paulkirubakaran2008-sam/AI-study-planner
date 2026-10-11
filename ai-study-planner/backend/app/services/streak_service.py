"""Streaks. A 'study day' is a day with >= 10 minutes of real study (focus-timer minutes or completed tasks)."""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from .. import models as m

MIN_STUDY_MINUTES = 10


def study_days(db: Session, user_id: int) -> set[date]:
    rows = (db.query(m.Progress.day).filter(m.Progress.user_id == user_id,
                                            m.Progress.actual_minutes >= MIN_STUDY_MINUTES).all())
    return {r[0] for r in rows}


def compute(days: set[date], today: date) -> tuple[int, int]:
    """Returns (current, longest). The streak stays alive through today until the day is over."""
    if not days:
        return 0, 0
    ordered = sorted(days)
    longest = run = 1
    for a, b in zip(ordered, ordered[1:]):
        run = run + 1 if (b - a).days == 1 else 1
        longest = max(longest, run)
    anchor = today if today in days else today - timedelta(days=1)
    current = 0
    d = anchor
    while d in days:
        current += 1
        d -= timedelta(days=1)
    return current, max(longest, current)


def summary(db: Session, user_id: int, today: date) -> dict:
    days = study_days(db, user_id)
    current, longest = compute(days, today)
    total_minutes = db.query(m.Progress.actual_minutes).filter(m.Progress.user_id == user_id).all()
    tasks_done = db.query(m.StudyTask).filter(m.StudyTask.user_id == user_id, m.StudyTask.status == "completed").count()
    return {"current": current, "longest": longest, "studied_today": today in days,
            "total_hours": round(sum(r[0] for r in total_minutes) / 60, 1), "tasks_completed": tasks_done}
