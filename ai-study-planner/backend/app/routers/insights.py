from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as sc
from ..database import get_db
from ..security import current_user
from ..services import ai_service, analytics_service as analytics, assistant_service as assistant
from ..services import dashboard_service, notification_service, planner_service as planner
from ..services import recommendation_service as reco
from ..timeutil import local_now
from .planner import _sync
from .common import replan

router = APIRouter(prefix="/api", tags=["insights"])


@router.get("/dashboard")
def dashboard(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    now = local_now(user.preferences.timezone)
    sync_result = _sync(db, user) if user.preferences.onboarded else {"missed": 0, "moved": [], "replanned": False}
    data = dashboard_service.build(db, user, now)
    notification_service.generate(db, user, now)
    db.commit()
    out = {k: v for k, v in data.items() if k not in ("today_tasks", "priority_task", "recommendation")}
    out["today_tasks"] = [sc.task_out(t) for t in data["today_tasks"]]
    out["priority_task"] = sc.task_out(data["priority_task"]) if data["priority_task"] else None
    out["recommendation"] = sc.RecommendationOut.model_validate(data["recommendation"]) if data["recommendation"] else None
    out["sync"] = sync_result
    return out


@router.get("/analytics")
def get_analytics(days: int = Query(7, ge=7, le=90), user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    return analytics.report(db, user, local_now(user.preferences.timezone).date(), days)


# ------------------------------------------------------------------ recommendations
@router.get("/recommendations")
def list_recommendations(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    recs = reco.sorted_active(reco.refresh(db, user))
    db.commit()
    return {"items": [sc.RecommendationOut.model_validate(r) for r in recs], "ai": ai_service.usage_today(db, user)}


def _rec(db: Session, user: m.User, rid: int) -> m.AIRecommendation:
    r = db.query(m.AIRecommendation).filter(m.AIRecommendation.id == rid, m.AIRecommendation.user_id == user.id).first()
    if not r:
        raise HTTPException(404, "Recommendation not found")
    return r


@router.post("/recommendations/{rid}/apply")
def apply_recommendation(rid: int, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    r = _rec(db, user, rid)
    if not r.action:
        raise HTTPException(422, "This recommendation has no action to apply.")
    actions, errors = assistant.validate_actions([r.action])
    if errors or not actions:
        raise HTTPException(422, errors[0] if errors else "Invalid action")
    results = assistant.execute(db, user, actions)
    if any(x["ok"] for x in results):
        r.status = "applied"
    db.commit()
    return {"results": results}


@router.post("/recommendations/{rid}/dismiss", status_code=204)
def dismiss_recommendation(rid: int, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    _rec(db, user, rid).status = "dismissed"
    db.commit()


@router.post("/recommendations/{rid}/explain")
def explain_recommendation(rid: int, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    r = _rec(db, user, rid)
    if r.ai_explanation:
        return {"available": True, "explanation": r.ai_explanation, "cached": True}
    try:
        text = reco.explain(db, user, r)
        db.commit()
        return {"available": True, "explanation": text, "cached": False}
    except ai_service.AIUnavailable:
        return {"available": False, "message": ai_service.UNAVAILABLE_MESSAGE}


@router.post("/recommendations/strategy")
def strategy(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        text, cached = reco.strategy(db, user)
        db.commit()
        return {"available": True, "tips": [ln.strip("-•* \t") for ln in text.splitlines() if ln.strip()][:4], "cached": cached}
    except ai_service.AIUnavailable:
        return {"available": False, "message": ai_service.UNAVAILABLE_MESSAGE}


@router.get("/ai/status")
def ai_status(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    return ai_service.usage_today(db, user)


# ------------------------------------------------------------------ assistant
@router.post("/assistant/interpret")
def interpret(body: sc.AssistantIn, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    out = assistant.interpret(db, user, body.text)
    db.commit()
    return out


@router.post("/assistant/apply")
def apply(body: sc.AssistantApplyIn, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    actions, errors = assistant.validate_actions(body.actions)
    if not actions:
        raise HTTPException(422, errors[0] if errors else "No valid actions")
    results = assistant.execute(db, user, actions)
    db.commit()
    return {"results": results, "errors": errors}


# ------------------------------------------------------------------ notifications
@router.get("/notifications")
def notifications(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    notification_service.generate(db, user)
    db.commit()
    rows = (db.query(m.Notification).filter(m.Notification.user_id == user.id).order_by(m.Notification.id.desc()).limit(40).all())
    return {"items": [sc.NotificationOut.model_validate(n) for n in rows], "unread": sum(1 for n in rows if not n.read)}


@router.post("/notifications/{nid}/read", status_code=204)
def read_notification(nid: int, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    n = db.query(m.Notification).filter(m.Notification.id == nid, m.Notification.user_id == user.id).first()
    if n:
        n.read = True
        db.commit()


@router.post("/notifications/read-all", status_code=204)
def read_all(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    db.query(m.Notification).filter(m.Notification.user_id == user.id, m.Notification.read.is_(False)).update({"read": True})
    db.commit()
