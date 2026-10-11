"""Analytics + study score, all computed from stored tasks and sessions (nothing synthetic).

Actual study minutes for a day = minutes tracked by focus/pomodoro sessions
                                 + planned minutes of tasks ticked off *without* a timer (self-reported credit).

STUDY SCORE (0-100), over a trailing 7-day window:
  Consistency (30%) = 70% * min(1, studied_days/5) + 30% * min(1, current_streak/7)
  Completion  (30%) = completed / tasks that were due (completed + skipped + overdue)
  Focus       (20%) = 50% * session finish ratio (sum(min(actual, planned)) / sum(planned))
                    + 50% * timer coverage (timer minutes / all credited minutes)
  Planning    (20%) = 60% * (1 - overloaded-day ratio) + 40% * plan coverage (days in next 7 that have tasks, when
                      capacity exists)
"""
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from .. import models as m
from . import planner_service as planner
from . import streak_service

DUE = ("completed", "skipped", "overdue")


def _range(db: Session, user_id: int, start: date, end: date):
    tasks = db.query(m.StudyTask).filter(m.StudyTask.user_id == user_id, m.StudyTask.date >= start,
                                         m.StudyTask.date <= end).all()
    sessions = db.query(m.StudySession).filter(m.StudySession.user_id == user_id, m.StudySession.local_date >= start,
                                               m.StudySession.local_date <= end).all()
    return tasks, sessions


def _actual_by_day(tasks, sessions) -> tuple[dict, dict, dict]:
    """(minutes per day, minutes per subject, timer-minutes per day)"""
    per_day, per_subject, timer = defaultdict(int), defaultdict(int), defaultdict(int)
    tasks_with_session = {s.task_id for s in sessions if s.task_id}
    for s in sessions:
        per_day[s.local_date] += s.duration_minutes
        timer[s.local_date] += s.duration_minutes
        if s.subject_id:
            per_subject[s.subject_id] += s.duration_minutes
    for t in tasks:
        if t.status == "completed" and t.id not in tasks_with_session:
            per_day[t.date] += t.actual_minutes or t.duration_minutes
            per_subject[t.subject_id] += t.actual_minutes or t.duration_minutes
    return per_day, per_subject, timer


def refresh_day(db: Session, user: m.User, day: date) -> m.Progress:
    tasks, sessions = _range(db, user.id, day, day)
    per_day, _, _ = _actual_by_day(tasks, sessions)
    row = db.query(m.Progress).filter_by(user_id=user.id, day=day).first()
    if row is None:
        row = m.Progress(user_id=user.id, day=day)
        db.add(row)
    row.planned_minutes = sum(t.duration_minutes for t in tasks if t.status != "skipped")
    row.actual_minutes = per_day.get(day, 0)
    row.tasks_planned = len(tasks)
    row.tasks_completed = sum(1 for t in tasks if t.status == "completed")
    row.tasks_missed = sum(1 for t in tasks if t.status in ("skipped", "overdue"))
    row.focus_sessions = len(sessions)
    db.flush()
    return row


def study_score(db: Session, user: m.User, today: date, window: int = 7) -> dict:
    start = today - timedelta(days=window - 1)
    tasks, sessions = _range(db, user.id, start, today)
    per_day, _, timer = _actual_by_day(tasks, sessions)
    studied_days = sum(1 for v in per_day.values() if v >= streak_service.MIN_STUDY_MINUTES)
    streak = streak_service.summary(db, user.id, today)["current"]
    consistency = 0.7 * min(1, studied_days / 5) + 0.3 * min(1, streak / 7)

    due = [t for t in tasks if t.status in DUE]
    completion = (sum(1 for t in due if t.status == "completed") / len(due)) if due else 0.0

    planned = sum(s.planned_minutes for s in sessions if s.planned_minutes)
    finish = (sum(min(s.duration_minutes, s.planned_minutes) for s in sessions if s.planned_minutes) / planned) if planned else 0.0
    credited = sum(per_day.values())
    coverage = (sum(timer.values()) / credited) if credited else 0.0
    focus = 0.5 * finish + 0.5 * coverage

    fut_end = today + timedelta(days=6)
    fut_tasks = db.query(m.StudyTask).filter(m.StudyTask.user_id == user.id, m.StudyTask.date >= today,
                                             m.StudyTask.date <= fut_end, m.StudyTask.status.in_(planner.ACTIVE)).all()
    days_with = {t.date for t in fut_tasks}
    cap_days = [today + timedelta(days=i) for i in range(7) if planner.day_capacity(user.preferences, today + timedelta(days=i)) > 0]
    cover = (len([d for d in cap_days if d in days_with]) / len(cap_days)) if cap_days else 1.0
    by_day = defaultdict(int)
    for t in fut_tasks + [t for t in tasks if t.status in planner.ACTIVE and t.date < today]:
        by_day[t.date] += t.duration_minutes
    over = sum(1 for v in by_day.values() if v > user.preferences.max_daily_minutes)
    over_ratio = over / len(by_day) if by_day else 0.0
    planning = 0.6 * (1 - over_ratio) + 0.4 * cover

    total = 0.30 * consistency + 0.30 * completion + 0.20 * focus + 0.20 * planning
    f = lambda x: int(round(x * 100))
    return {"score": f(total), "consistency": f(consistency), "completion": f(completion), "focus": f(focus),
            "planning": f(planning), "window_days": window,
            "has_data": bool(tasks or sessions)}


def report(db: Session, user: m.User, today: date, days: int = 7) -> dict:
    start = today - timedelta(days=days - 1)
    tasks, sessions = _range(db, user.id, start, today)
    per_day, per_subject, timer = _actual_by_day(tasks, sessions)
    names = {s.id: (s.name, s.color) for s in user.subjects}
    series = []
    for i in range(days):
        d = start + timedelta(days=i)
        day_tasks = [t for t in tasks if t.date == d]
        series.append({"date": d, "actual_minutes": per_day.get(d, 0),
                       "planned_minutes": sum(t.duration_minutes for t in day_tasks if t.status != "skipped"),
                       "completed": sum(1 for t in day_tasks if t.status == "completed"),
                       "missed": sum(1 for t in day_tasks if t.status in ("skipped", "overdue"))})
    due = [t for t in tasks if t.status in DUE]
    done = [t for t in due if t.status == "completed"]
    total_actual = sum(per_subject.values())
    distribution = [{"subject_id": sid, "name": names.get(sid, ("Other", "#888"))[0],
                     "color": names.get(sid, ("Other", "#888"))[1], "minutes": mins,
                     "share": round(mins / total_actual * 100) if total_actual else 0}
                    for sid, mins in sorted(per_subject.items(), key=lambda kv: -kv[1])]
    conf = [s.confidence for s in sessions if s.confidence]
    return {
        "range_days": days,
        "series": series,
        "completion_rate": round(len(done) / len(due) * 100) if due else 0,
        "subject_distribution": distribution,
        "productivity": {
            "planned_minutes": sum(x["planned_minutes"] for x in series),
            "actual_minutes": sum(per_day.values()),
            "completion_rate": round(len(done) / len(due) * 100) if due else 0,
            "focus_sessions": len(sessions),
            "missed_tasks": sum(1 for t in tasks if t.status in ("skipped", "overdue")),
            "avg_confidence": round(sum(conf) / len(conf), 1) if conf else None,
        },
        "score": study_score(db, user, today),
        "streak": streak_service.summary(db, user.id, today),
        "topics": [{"subject": s.name, "color": s.color, "name": t.name, "mastery": t.mastery}
                   for s in user.subjects for t in s.topics],
    }
