from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from .. import models as m
from .. import schemas as sc
from ..database import get_db
from ..security import current_user
from ..services import analytics_service as analytics
from ..services import notification_service, planner_service as planner, priority_service as ps, task_service
from ..timeutil import local_now, parse_hhmm

router = APIRouter(prefix="/api", tags=["planner"])


def _task(db: Session, user: m.User, tid: int) -> m.StudyTask:
    t = db.query(m.StudyTask).options(joinedload(m.StudyTask.subject), joinedload(m.StudyTask.topic)).filter(
        m.StudyTask.id == tid, m.StudyTask.user_id == user.id).first()
    if not t:
        raise HTTPException(404, "Task not found")
    return t


def _check_overlap(db: Session, user: m.User, t_id: int | None, day: date, start: int, dur: int, now: datetime) -> int:
    """Return a start minute that doesn't overlap another session (nearest free slot if needed)."""
    others = db.query(m.StudyTask).filter(m.StudyTask.user_id == user.id, m.StudyTask.date == day,
                                          m.StudyTask.status.in_(planner.ACTIVE), m.StudyTask.id != (t_id or -1)).all()
    if not any(start < o.start_minute + o.duration_minutes and start + dur > o.start_minute for o in others):
        return start
    alloc = planner.build_allocator(db, user, day, now, tasks=[o for o in others])
    s = alloc.find(dur, earliest=start)
    if s is None:
        raise HTTPException(409, "That time overlaps another session and there's no free slot nearby.")
    return s


def _sync(db: Session, user: m.User) -> dict:
    now = local_now(user.preferences.timezone)
    res = planner.sync(db, user, now)
    if res["missed"]:
        analytics.refresh_day(db, user, now.date())
    return res


@router.post("/planner/generate")
def generate(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    s = planner.generate(db, user)
    db.commit()
    return {"created": s.created, "planned_minutes": s.planned_minutes, "warnings": s.warnings, "horizon_end": s.horizon_end}


@router.post("/planner/sync")
def sync(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    res = _sync(db, user)
    notification_service.generate(db, user)
    db.commit()
    return res


@router.get("/planner/overview")
def overview(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    now = local_now(user.preferences.timezone)
    today = now.date()
    pending = db.query(m.StudyTask).filter(m.StudyTask.user_id == user.id, m.StudyTask.date >= today,
                                           m.StudyTask.status.in_(("pending", "in_progress"))).all()
    per_subject = {}
    for t in pending:
        per_subject[t.subject_id] = per_subject.get(t.subject_id, 0) + t.duration_minutes
    subjects = []
    for s in user.subjects:
        exam = planner.subject_exam(s, today)
        need = sum(ps.minutes_needed(t.mastery, t.difficulty, s.target_marks) for t in s.topics)
        subjects.append({"subject_id": s.id, "name": s.name, "color": s.color, "planned_minutes": per_subject.get(s.id, 0),
                         "needed_minutes": need, "exam_date": exam, "days_left": (exam - today).days if exam else None})
    last = max([x["exam_date"] for x in subjects if x["exam_date"]] + [today])
    capacity = sum(planner.day_capacity(user.preferences, today + timedelta(days=i)) for i in range((last - today).days))
    return {"today": today, "subjects": subjects, "pending_minutes": sum(per_subject.values()), "capacity_minutes": capacity,
            "overloaded_days": planner.overload_report(db, user, today, today + timedelta(days=30)),
            "last_planned_at": user.preferences.last_planned_at, "max_daily_minutes": user.preferences.max_daily_minutes,
            "weights": ps.WEIGHTS}


@router.post("/planner/rebalance")
def rebalance(body: sc.RebalanceIn, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    res = planner.rebalance_day(db, user, body.date)
    db.commit()
    return res


# ------------------------------------------------------------------ tasks
@router.get("/tasks", response_model=list[sc.TaskOut])
def list_tasks(start: date | None = None, end: date | None = None, status: str | None = None, subject_id: int | None = None,
               user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    now = local_now(user.preferences.timezone)
    if user.preferences.onboarded:
        _sync(db, user)
        db.commit()
    start = start or now.date() - timedelta(days=7)
    end = end or now.date() + timedelta(days=45)
    if (end - start).days > 400:
        raise HTTPException(422, "Date range too large")
    q = (db.query(m.StudyTask).options(joinedload(m.StudyTask.subject), joinedload(m.StudyTask.topic))
         .filter(m.StudyTask.user_id == user.id, m.StudyTask.date >= start, m.StudyTask.date <= end))
    if status:
        q = q.filter(m.StudyTask.status == status)
    if subject_id:
        q = q.filter(m.StudyTask.subject_id == subject_id)
    return [sc.task_out(t) for t in q.order_by(m.StudyTask.date, m.StudyTask.start_minute).limit(2000).all()]


@router.post("/tasks", response_model=sc.TaskOut, status_code=201)
def create_task(body: sc.TaskIn, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    now = local_now(user.preferences.timezone)
    subj = db.query(m.Subject).filter(m.Subject.id == body.subject_id, m.Subject.user_id == user.id).first()
    if not subj:
        raise HTTPException(404, "Subject not found")
    topic = None
    if body.topic_id:
        topic = db.query(m.Topic).filter(m.Topic.id == body.topic_id, m.Topic.subject_id == subj.id).first()
        if not topic:
            raise HTTPException(404, "Topic not found")
    start = _check_overlap(db, user, None, body.date, parse_hhmm(body.start_time), body.duration_minutes, now)
    if start + body.duration_minutes > 24 * 60:
        raise HTTPException(422, "A session can't run past midnight.")
    prio, score = body.priority, 0.0
    if topic:
        p = ps.compute(mastery=topic.mastery, topic_difficulty=topic.difficulty, subject_importance=subj.importance,
                       target_marks=subj.target_marks, miss_count=topic.miss_count, last_studied=topic.last_studied,
                       exam_date=planner.subject_exam(subj, body.date), on_date=body.date)
        prio, score = body.priority or p.level, p.score
    t = m.StudyTask(user_id=user.id, subject_id=subj.id, topic_id=topic.id if topic else None,
                    title=(body.title or (topic.name if topic else subj.name)).strip(), task_type=body.task_type, date=body.date,
                    start_minute=start, duration_minutes=body.duration_minutes, priority=prio or "medium", priority_score=score,
                    difficulty=body.difficulty or (topic.difficulty if topic else subj.difficulty), origin="manual", locked=True,
                    notes=body.notes, reason="Added by you")
    db.add(t)
    db.commit()
    return sc.task_out(_task(db, user, t.id))


@router.put("/tasks/{tid}", response_model=sc.TaskOut)
def update_task(tid: int, body: sc.TaskUpdate, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    t = _task(db, user, tid)
    data = body.model_dump(exclude_unset=True)
    now = local_now(user.preferences.timezone)
    if t.status == "completed" and {"date", "start_time", "duration_minutes"} & data.keys():
        raise HTTPException(409, "Completed sessions can't be moved. Add a new session instead.")
    if "status" in data and data["status"] not in (None, "pending", "in_progress"):
        raise HTTPException(422, "Use the Complete or Skip actions to change a session's status.")
    moved = False
    new_date = data.get("date", t.date)
    new_start = parse_hhmm(data["start_time"]) if data.get("start_time") else t.start_minute
    new_dur = data.get("duration_minutes", t.duration_minutes)
    if {"date", "start_time", "duration_minutes"} & data.keys():
        if new_date < now.date():
            raise HTTPException(422, "You can't schedule a session in the past.")
        if new_date == now.date() and new_start + new_dur <= now.hour * 60 + now.minute and ("date" in data or "start_time" in data):
            raise HTTPException(422, "That time has already passed.")
        new_start = _check_overlap(db, user, t.id, new_date, new_start, new_dur, now)
        if new_start + new_dur > 24 * 60:
            raise HTTPException(422, "A session can't run past midnight.")
        moved = (new_date, new_start) != (t.date, t.start_minute)
        if moved and t.moved_from is None:
            t.moved_from = t.date
        t.date, t.start_minute, t.duration_minutes = new_date, new_start, new_dur
        t.locked = True
        if moved:
            t.reschedule_count += 1
            t.reason = "Moved by you"
    for f in ("title", "priority", "notes"):
        if data.get(f) is not None:
            setattr(t, f, data[f].strip() if isinstance(data[f], str) else data[f])
    if data.get("status") in ("pending", "in_progress"):
        t.status = data["status"]
        if t.status == "pending":
            t.handled = False
    db.commit()
    return sc.task_out(_task(db, user, tid))


@router.delete("/tasks/{tid}", status_code=204)
def delete_task(tid: int, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    t = _task(db, user, tid)
    day = t.date
    db.delete(t)
    db.flush()
    analytics.refresh_day(db, user, day)
    db.commit()


@router.post("/tasks/{tid}/start", response_model=sc.TaskOut)
def start_task(tid: int, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    t = _task(db, user, tid)
    if t.status in ("pending", "overdue"):
        t.status = "in_progress"
    db.commit()
    return sc.task_out(t)


@router.post("/tasks/{tid}/complete")
def complete(tid: int, body: sc.CompleteIn, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    t = _task(db, user, tid)
    if t.status == "completed":
        raise HTTPException(409, "Already completed.")
    res = task_service.complete_task(db, user, t, body.confidence, body.actual_minutes)
    db.commit()
    nxt = res["next_review"]
    return {"task": sc.task_out(_task(db, user, tid)),
            "next_review": {"date": nxt.date, "start_time": f"{nxt.start_minute // 60:02d}:{nxt.start_minute % 60:02d}"} if nxt else None}


@router.post("/tasks/{tid}/skip")
def skip(tid: int, body: sc.SkipIn, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    t = _task(db, user, tid)
    if t.status == "completed":
        raise HTTPException(409, "Completed sessions can't be skipped.")
    res = task_service.skip_task(db, user, t, body.reschedule)
    db.commit()
    return {"task": sc.task_out(_task(db, user, tid)), "moved": res["moved"], "replanned": res["replanned"]}


@router.post("/sessions", status_code=201)
def record_session(body: sc.SessionIn, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    task = _task(db, user, body.task_id) if body.task_id else None
    if not task and body.subject_id:
        if not db.query(m.Subject).filter(m.Subject.id == body.subject_id, m.Subject.user_id == user.id).first():
            raise HTTPException(404, "Subject not found")
    sess = task_service.record_session(db, user, task=task, subject_id=body.subject_id, topic_id=body.topic_id,
                                       minutes=body.duration_minutes, planned=body.planned_minutes, mode=body.mode,
                                       confidence=body.confidence, complete=body.complete_task)
    db.commit()
    return {"id": sess.id}
