"""Spaced repetition. Ladder: review after 1, 3, 7, 14, 30 days.

* Low confidence (1-2)  -> go back a rung and review *earlier* (half the interval, min 1 day).
* Medium (3)            -> next rung.
* High (4)              -> next rung.
* Very high (5)         -> skip a rung (interval grows faster).
Reviews are never scheduled on/after the exam day: they are pulled back to the day before.
"""
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from .. import models as m
from ..timeutil import local_now
from . import planner_service as planner
from . import priority_service as ps

LADDER = [1, 3, 7, 14, 30]
MASTERY_DELTA = {1: -2, 2: 1, 3: 4, 4: 7, 5: 10}
REVIEW_MINUTES = 20


def apply_confidence(topic: m.Topic, confidence: int, minutes: int, task_type: str, day: date) -> None:
    scale = min(1.5, max(0.3, minutes / 45)) * (0.6 if task_type == "revision" else 1.0)
    delta = MASTERY_DELTA[confidence] * scale
    topic.mastery = int(max(0, min(100, round(topic.mastery + delta))))
    topic.last_confidence = confidence
    topic.last_studied = day


def next_stage_and_interval(stage: int, confidence: int, was_review: bool) -> tuple[int, int]:
    top = len(LADDER) - 1
    if not was_review:
        new = 0 if confidence <= 3 else 1
        interval = LADDER[new] if confidence >= 3 else 1
        return new, interval
    if confidence <= 2:
        new = max(0, stage - 1)
        return new, max(1, LADDER[new] // 2)
    new = min(top, stage + (2 if confidence == 5 else 1))
    return new, LADDER[new]


def _place_review(db: Session, user: m.User, topic: m.Topic, subject: m.Subject, due: date, exam: date | None,
                  now: datetime, note: str, moved_from: date | None = None) -> m.StudyTask | None:
    latest = (exam - timedelta(days=1)) if exam else due + timedelta(days=7)
    for off in (0, 1, -1, 2, 3):
        d = due + timedelta(days=off)
        if d < now.date() or d > latest:
            continue
        s = planner.find_free_slot(db, user, d, REVIEW_MINUTES, now=now)
        if s is not None:
            p = ps.compute(mastery=topic.mastery, topic_difficulty=topic.difficulty, subject_importance=subject.importance,
                           target_marks=subject.target_marks, miss_count=topic.miss_count, last_studied=topic.last_studied,
                           exam_date=exam, on_date=d)
            level = p.level if ps.LEVEL_RANK[p.level] >= 1 else "medium"
            t = m.StudyTask(user_id=user.id, subject_id=subject.id, topic_id=topic.id, title=topic.name,
                            task_type="revision", date=d, start_minute=s, duration_minutes=REVIEW_MINUTES,
                            priority=level, priority_score=p.score, difficulty=topic.difficulty, origin="spaced",
                            reason=note[:240], moved_from=moved_from)
            db.add(t)
            return t
    return None


def schedule_next_review(db: Session, user: m.User, task: m.StudyTask, confidence: int, now: datetime | None = None):
    topic, subject = task.topic, task.subject
    if topic is None:
        return None
    now = now or local_now(user.preferences.timezone)
    was_review = task.task_type == "revision"
    stage, interval = next_stage_and_interval(topic.review_stage, confidence, was_review)
    topic.review_stage = stage
    # replace any other pending spaced review for this topic
    for old in db.query(m.StudyTask).filter(m.StudyTask.topic_id == topic.id, m.StudyTask.origin == "spaced",
                                            m.StudyTask.status == "pending", m.StudyTask.id != task.id).all():
        db.delete(old)
    exam = planner.subject_exam(subject, now.date())
    due = now.date() + timedelta(days=interval)
    if exam and due >= exam:
        due = exam - timedelta(days=1)
    if due <= now.date() and not (due == now.date() and interval == 0):
        due = now.date() + timedelta(days=1)
        if exam and due >= exam:
            return None
    why = ("Quick review sooner because confidence was low" if confidence <= 2 else
           f"Spaced review: {interval} day{'s' if interval != 1 else ''} after studying")
    return _place_review(db, user, topic, subject, due, exam, now, why)


def reschedule_review(db: Session, user: m.User, task: m.StudyTask, now: datetime) -> m.StudyTask | None:
    exam = planner.subject_exam(task.subject, now.date())
    due = now.date() + timedelta(days=1)
    if exam and due >= exam:
        due = now.date()
    return _place_review(db, user, task.topic, task.subject, due, exam, now, "Spaced review moved after a missed session",
                         moved_from=task.date) if task.topic else None
