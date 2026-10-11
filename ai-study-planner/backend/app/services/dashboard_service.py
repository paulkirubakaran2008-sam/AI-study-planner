from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from .. import models as m
from ..timeutil import local_now
from . import analytics_service as analytics
from . import planner_service as planner
from . import priority_service as ps
from . import recommendation_service as reco
from . import streak_service


def preparation(subject: m.Subject) -> int:
    """Difficulty-weighted mean mastery of a subject's topics."""
    if not subject.topics:
        return 0
    w = sum(t.difficulty for t in subject.topics)
    return int(round(sum(t.mastery * t.difficulty for t in subject.topics) / w))


def next_exam(user: m.User, now: datetime) -> dict | None:
    best = None
    for s in user.subjects:
        for e in s.exams:
            at = datetime.combine(e.exam_date, datetime.min.time()) + timedelta(minutes=e.start_minute)
            if at > now and (best is None or at < best[0]):
                best = (at, s, e)
    if not best:
        return None
    at, s, e = best
    weak = sorted(s.topics, key=lambda t: t.mastery)[:2]
    return {"subject_id": s.id, "subject": s.name, "color": s.color, "exam_date": e.exam_date, "title": e.title,
            "seconds_remaining": int((at - now).total_seconds()), "days_left": (e.exam_date - now.date()).days,
            "preparation": preparation(s),
            "recommended": ("Study " + " and ".join(t.name for t in weak) + " today.") if weak else "Add topics to get a recommendation."}


def build(db: Session, user: m.User, now: datetime) -> dict:
    today = now.date()
    todays = (db.query(m.StudyTask).filter(m.StudyTask.user_id == user.id, m.StudyTask.date == today,
                                           m.StudyTask.status != "skipped").order_by(m.StudyTask.start_minute).all())
    open_tasks = [t for t in todays if t.status in ("pending", "in_progress")]
    done = [t for t in todays if t.status == "completed"]
    minute = now.hour * 60 + now.minute
    priority_task = None
    if open_tasks:
        priority_task = sorted(open_tasks, key=lambda t: (-ps.LEVEL_RANK[t.priority], -t.priority_score, t.start_minute))[0]
    else:
        nxt = (db.query(m.StudyTask).filter(m.StudyTask.user_id == user.id, m.StudyTask.date > today, m.StudyTask.status == "pending")
               .order_by(m.StudyTask.date, m.StudyTask.start_minute).first())
        priority_task = nxt
    prog = analytics.refresh_day(db, user, today)
    week = analytics.report(db, user, today, 7)
    recs = reco.sorted_active(reco.refresh(db, user, now))
    hour = now.hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
    remaining_all = db.query(m.StudyTask).filter(m.StudyTask.user_id == user.id, m.StudyTask.date >= today,
                                                 m.StudyTask.status.in_(("pending", "in_progress"))).count()
    return {
        "greeting": greeting, "name": user.name, "today": today, "now_minute": minute,
        "stats": {"study_minutes_today": prog.actual_minutes, "planned_minutes_today": sum(t.duration_minutes for t in todays),
                  "completion_rate_week": week["completion_rate"], "tasks_today": len(todays), "tasks_done_today": len(done),
                  "remaining_today": len(open_tasks), "remaining_total": remaining_all,
                  "completion_today": round(len(done) / len(todays) * 100) if todays else 0},
        "streak": streak_service.summary(db, user.id, today),
        "score": week["score"],
        "today_tasks": todays, "priority_task": priority_task,
        "next_exam": next_exam(user, now),
        "recommendation": recs[0] if recs else None,
        "exams": [{"subject": s.name, "color": s.color, "date": e.exam_date, "days_left": (e.exam_date - today).days,
                   "preparation": preparation(s)} for s in user.subjects for e in s.exams if e.exam_date >= today],
        "warnings": [{"date": r["date"], "planned_minutes": r["planned_minutes"], "recommended_max": r["recommended_max"]}
                     for r in planner.overload_report(db, user, today, today + timedelta(days=14))],
        "week_series": week["series"],
    }
