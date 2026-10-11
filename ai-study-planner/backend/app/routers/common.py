from datetime import date

from sqlalchemy.orm import Session

from .. import models as m
from ..services import dashboard_service, planner_service as planner
from ..timeutil import local_now
from .. import schemas as sc


def subject_out(s: m.Subject, today: date) -> sc.SubjectOut:
    exam = planner.subject_exam(s, today) or (max((e.exam_date for e in s.exams), default=None))
    return sc.SubjectOut(id=s.id, name=s.name, color=s.color, difficulty=s.difficulty, importance=s.importance,
                         target_marks=s.target_marks, exam_date=exam, days_left=(exam - today).days if exam else None,
                         preparation=dashboard_service.preparation(s),
                         topics=[sc.TopicOut.model_validate(t) for t in s.topics])


def replan(db: Session, user: m.User) -> None:
    """Re-run the (pure algorithm) planner after any data change. Cheap; never calls AI."""
    if user.preferences.onboarded:
        db.expire(user, ["subjects"])
        planner.generate(db, user)


def upsert_exam(db: Session, user: m.User, subject: m.Subject, exam_date: date | None) -> None:
    upcoming = sorted(subject.exams, key=lambda e: e.exam_date)
    if exam_date is None:
        return
    if upcoming:
        upcoming[-1].exam_date = exam_date if len(upcoming) == 1 else upcoming[-1].exam_date
        if len(upcoming) > 1:
            upcoming[0].exam_date = exam_date
    else:
        db.add(m.Exam(user_id=user.id, subject_id=subject.id, title="Final exam", exam_date=exam_date))
