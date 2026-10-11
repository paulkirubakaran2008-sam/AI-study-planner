from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as sc
from ..database import get_db
from ..security import current_user
from ..timeutil import local_now
from .common import replan, subject_out, upsert_exam

router = APIRouter(prefix="/api", tags=["subjects"])
PALETTE = ["#3B5BDB", "#E8590C", "#0CA678", "#AE3EC9", "#F08C00", "#1098AD", "#D6336C", "#5C7CFA"]


def _subject(db: Session, user: m.User, sid: int) -> m.Subject:
    s = db.query(m.Subject).filter(m.Subject.id == sid, m.Subject.user_id == user.id).first()
    if not s:
        raise HTTPException(404, "Subject not found")
    return s


def _topic(db: Session, user: m.User, tid: int) -> m.Topic:
    t = (db.query(m.Topic).join(m.Subject).filter(m.Topic.id == tid, m.Subject.user_id == user.id).first())
    if not t:
        raise HTTPException(404, "Topic not found")
    return t


@router.get("/subjects", response_model=list[sc.SubjectOut])
def list_subjects(user: m.User = Depends(current_user)):
    today = local_now(user.preferences.timezone).date()
    return [subject_out(s, today) for s in user.subjects]


@router.post("/subjects", response_model=sc.SubjectOut, status_code=201)
def create_subject(body: sc.SubjectIn, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    if len(user.subjects) >= 15:
        raise HTTPException(422, "You can track up to 15 subjects.")
    if any(s.name.lower() == body.name.strip().lower() for s in user.subjects):
        raise HTTPException(409, "You already have a subject with that name.")
    s = m.Subject(user_id=user.id, name=body.name.strip(), color=body.color or PALETTE[len(user.subjects) % len(PALETTE)],
                  difficulty=body.difficulty, importance=body.importance, target_marks=body.target_marks)
    db.add(s)
    db.flush()
    db.refresh(s)
    upsert_exam(db, user, s, body.exam_date)
    for j, t in enumerate(body.topics):
        db.add(m.Topic(subject_id=s.id, name=t.name.strip(), difficulty=t.difficulty, mastery=t.mastery, position=j))
    db.flush()
    db.refresh(s)
    replan(db, user)
    db.commit()
    return subject_out(s, local_now(user.preferences.timezone).date())


@router.put("/subjects/{sid}", response_model=sc.SubjectOut)
def update_subject(sid: int, body: sc.SubjectUpdate, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    s = _subject(db, user, sid)
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"]:
        if any(o.id != s.id and o.name.lower() == data["name"].strip().lower() for o in user.subjects):
            raise HTTPException(409, "You already have a subject with that name.")
        s.name = data["name"].strip()
    for f in ("color", "difficulty", "importance", "target_marks"):
        if data.get(f) is not None:
            setattr(s, f, data[f])
    if data.get("clear_exam"):
        for e in list(s.exams):
            db.delete(e)
    elif data.get("exam_date"):
        upsert_exam(db, user, s, data["exam_date"])
    db.flush()
    db.refresh(s)
    replan(db, user)
    db.commit()
    return subject_out(s, local_now(user.preferences.timezone).date())


@router.delete("/subjects/{sid}", status_code=204)
def delete_subject(sid: int, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    s = _subject(db, user, sid)
    db.query(m.StudyTask).filter(m.StudyTask.subject_id == s.id, m.StudyTask.user_id == user.id,
                                 m.StudyTask.status.in_(("pending", "in_progress", "overdue"))).delete(synchronize_session=False)
    db.delete(s)
    db.flush()
    replan(db, user)
    db.commit()


@router.post("/subjects/{sid}/topics", response_model=sc.TopicOut, status_code=201)
def add_topic(sid: int, body: sc.TopicIn, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    s = _subject(db, user, sid)
    if len(s.topics) >= 60:
        raise HTTPException(422, "A subject can have up to 60 topics.")
    t = m.Topic(subject_id=s.id, name=body.name.strip(), difficulty=body.difficulty, mastery=body.mastery, position=len(s.topics))
    db.add(t)
    db.flush()
    db.refresh(s)
    replan(db, user)
    db.commit()
    return sc.TopicOut.model_validate(t)


@router.put("/topics/{tid}", response_model=sc.TopicOut)
def update_topic(tid: int, body: sc.TopicUpdate, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    t = _topic(db, user, tid)
    for f, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(t, f, v.strip() if isinstance(v, str) else v)
    db.flush()
    replan(db, user)
    db.commit()
    return sc.TopicOut.model_validate(t)


@router.delete("/topics/{tid}", status_code=204)
def delete_topic(tid: int, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    t = _topic(db, user, tid)
    db.query(m.StudyTask).filter(m.StudyTask.topic_id == t.id, m.StudyTask.status.in_(("pending", "in_progress", "overdue"))).delete(synchronize_session=False)
    db.delete(t)
    db.flush()
    replan(db, user)
    db.commit()
