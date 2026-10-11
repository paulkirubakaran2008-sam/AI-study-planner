from datetime import datetime

from sqlalchemy.orm import Session

from .. import models as m
from ..timeutil import local_now
from . import analytics_service as analytics
from . import planner_service as planner
from . import revision_service as revision


def complete_task(db: Session, user: m.User, task: m.StudyTask, confidence: int | None = None,
                  actual_minutes: int | None = None, now: datetime | None = None) -> dict:
    now = now or local_now(user.preferences.timezone)
    original = task.date
    task.status = "completed"
    task.completed_at = datetime.utcnow()
    task.confidence = confidence or task.confidence or 3
    task.actual_minutes = actual_minutes if actual_minutes is not None else (task.actual_minutes or task.duration_minutes)
    if task.date != now.date() and task.date < now.date():
        task.moved_from = task.moved_from or task.date
        task.date = now.date()                       # completed late: credit the day the work actually happened
    review = None
    if task.topic:
        revision.apply_confidence(task.topic, task.confidence, task.actual_minutes, task.task_type, now.date())
        review = revision.schedule_next_review(db, user, task, task.confidence, now)
    db.flush()
    analytics.refresh_day(db, user, now.date())
    if original != now.date():
        analytics.refresh_day(db, user, original)
    return {"next_review": review}


def skip_task(db: Session, user: m.User, task: m.StudyTask, reschedule: bool = True, now: datetime | None = None) -> dict:
    now = now or local_now(user.preferences.timezone)
    task.status = "skipped"
    task.handled = True
    if task.topic:
        task.topic.miss_count += 1
    moved: list[dict] = []
    replanned = False
    db.flush()
    if reschedule:
        if task.origin == "spaced":
            revision.reschedule_review(db, user, task, now)
        else:
            planner.generate(db, user, now)
            moved = planner.link_moved(db, user, [task], now)
            replanned = True
    analytics.refresh_day(db, user, task.date)
    return {"moved": moved, "replanned": replanned}


def record_session(db: Session, user: m.User, *, task: m.StudyTask | None, subject_id: int | None, topic_id: int | None,
                   minutes: int, planned: int, mode: str, confidence: int | None, complete: bool,
                   now: datetime | None = None) -> m.StudySession:
    now = now or local_now(user.preferences.timezone)
    sess = m.StudySession(user_id=user.id, task_id=task.id if task else None,
                          subject_id=task.subject_id if task else subject_id,
                          topic_id=task.topic_id if task else topic_id, local_date=now.date(),
                          duration_minutes=minutes, planned_minutes=planned, mode=mode, confidence=confidence)
    db.add(sess)
    db.flush()
    if task:
        if complete:
            total = sum(s.duration_minutes for s in db.query(m.StudySession).filter(m.StudySession.task_id == task.id))
            complete_task(db, user, task, confidence, total, now)
        elif task.status == "pending":
            task.status = "in_progress"
    elif topic_id and confidence:
        topic = db.get(m.Topic, topic_id)
        if topic:
            revision.apply_confidence(topic, confidence, minutes, "study", now.date())
    analytics.refresh_day(db, user, now.date())
    return sess
