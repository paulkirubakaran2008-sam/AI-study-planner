from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as sc
from ..database import get_db
from ..security import auth_limiter, create_token, current_user, demo_limiter, hash_password, verify_password
from ..services import demo_service, planner_service as planner
from ..timeutil import local_now, safe_zone
from .common import replan, upsert_exam

router = APIRouter(prefix="/api", tags=["auth"])
PALETTE = ["#3B5BDB", "#E8590C", "#0CA678", "#AE3EC9", "#F08C00", "#1098AD", "#D6336C", "#5C7CFA"]


def user_out(u: m.User) -> sc.UserOut:
    return sc.UserOut(id=u.id, name=u.name, email=u.email, college=u.college, department=u.department, year=u.year,
                      is_demo=u.is_demo, onboarded=u.preferences.onboarded, theme=u.preferences.theme)


def _token(u: m.User) -> sc.TokenOut:
    return sc.TokenOut(access_token=create_token(u.id), user=user_out(u))


@router.post("/auth/register", response_model=sc.TokenOut, status_code=201, dependencies=[Depends(auth_limiter)])
def register(body: sc.RegisterIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.query(m.User).filter(m.User.email == email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    tz = body.timezone if body.timezone and str(safe_zone(body.timezone)) == body.timezone else "Asia/Kolkata"
    user = m.User(email=email, name=body.name.strip(), password_hash=hash_password(body.password))
    user.preferences = m.StudyPreferences(timezone=tz)
    db.add(user)
    db.commit()
    return _token(user)


@router.post("/auth/login", response_model=sc.TokenOut, dependencies=[Depends(auth_limiter)])
def login(body: sc.LoginIn, db: Session = Depends(get_db)):
    user = db.query(m.User).filter(m.User.email == body.email.lower(), m.User.is_demo.is_(False)).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    return _token(user)


@router.post("/auth/logout", status_code=204)
def logout(user: m.User = Depends(current_user)):
    return None  # stateless JWT: the client discards the token


@router.get("/auth/me", response_model=sc.UserOut)
def me(user: m.User = Depends(current_user)):
    return user_out(user)


@router.post("/demo/start", response_model=sc.TokenOut, dependencies=[Depends(demo_limiter)])
def start_demo(body: sc.DemoIn, db: Session = Depends(get_db)):
    tz = body.timezone if body.timezone and str(safe_zone(body.timezone)) == body.timezone else None
    return _token(demo_service.create_demo_user(db, tz))


@router.delete("/account", status_code=204)
def delete_account(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(user)
    db.commit()


def _settings_out(u: m.User) -> sc.SettingsOut:
    p = u.preferences
    return sc.SettingsOut(name=u.name, college=u.college, department=u.department, year=u.year, timezone=p.timezone,
                          daily_minutes=p.daily_minutes, max_daily_minutes=p.max_daily_minutes, preferred_times=p.preferred_times,
                          max_block_minutes=p.max_block_minutes, break_minutes=p.break_minutes, target_marks=p.target_marks,
                          default_level=p.default_level, blocked_dates=p.blocked_dates or [], theme=p.theme,
                          notifications_enabled=p.notifications_enabled, browser_notifications=p.browser_notifications,
                          pomodoro=sc.PomodoroCfg(**p.pomodoro))


@router.get("/settings", response_model=sc.SettingsOut)
def get_settings_route(user: m.User = Depends(current_user)):
    return _settings_out(user)


SCHEDULING_FIELDS = {"daily_minutes", "max_daily_minutes", "preferred_times", "max_block_minutes", "break_minutes", "blocked_dates", "timezone"}


@router.put("/settings", response_model=sc.SettingsOut)
def update_settings(body: sc.SettingsIn, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    p = user.preferences
    for f in ("name", "college", "department", "year"):
        if f in data and data[f] is not None:
            setattr(user, f, data[f].strip() if isinstance(data[f], str) else data[f])
    if "timezone" in data and data["timezone"] and str(safe_zone(data["timezone"])) != data["timezone"]:
        raise HTTPException(422, "Unknown timezone")
    if "blocked_dates" in data and data["blocked_dates"] is not None:
        data["blocked_dates"] = sorted({d.isoformat() for d in data["blocked_dates"]})
    if "pomodoro" in data and data["pomodoro"] is not None:
        data["pomodoro"] = body.pomodoro.model_dump()
    for f in ("timezone", "daily_minutes", "max_daily_minutes", "preferred_times", "max_block_minutes", "break_minutes",
              "target_marks", "blocked_dates", "theme", "notifications_enabled", "browser_notifications", "pomodoro"):
        if f in data and data[f] is not None:
            setattr(p, f, data[f])
    if SCHEDULING_FIELDS & data.keys():
        replan(db, user)
    db.commit()
    return _settings_out(user)


@router.post("/onboarding", status_code=201)
def onboarding(body: sc.OnboardingIn, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    p = user.preferences
    if p.onboarded and not user.is_demo:
        raise HTTPException(409, "You've already completed setup. Use Subjects and Settings to change your data.")
    names = [s.name.strip().lower() for s in body.subjects]
    if len(set(names)) != len(names):
        raise HTTPException(422, "Subject names must be unique.")
    user.name, user.college, user.department, user.year = body.profile.name.strip(), body.profile.college.strip(), body.profile.department.strip(), body.profile.year
    if body.timezone and str(safe_zone(body.timezone)) == body.timezone:
        p.timezone = body.timezone
    p.daily_minutes = [body.weekday_minutes] * 5 + [body.weekend_minutes] * 2
    p.max_daily_minutes = max(180, min(480, max(body.weekday_minutes, body.weekend_minutes) + 60))
    p.preferred_times = body.preferred_times or ["morning", "evening"]
    p.default_level, p.target_marks = body.default_level, body.target_marks
    today = local_now(p.timezone).date()
    for i, s in enumerate(body.subjects):
        subj = m.Subject(user_id=user.id, name=s.name.strip(), color=s.color or PALETTE[i % len(PALETTE)], difficulty=s.difficulty,
                         importance=s.importance, target_marks=s.target_marks or body.target_marks)
        db.add(subj)
        db.flush()
        if s.exam_date:
            db.add(m.Exam(user_id=user.id, subject_id=subj.id, title="Final exam", exam_date=s.exam_date))
        for j, t in enumerate(s.topics):
            db.add(m.Topic(subject_id=subj.id, name=t.name.strip(), difficulty=t.difficulty or s.difficulty,
                           mastery=t.mastery if t.mastery is not None else body.default_level, position=j))
    p.onboarded = True
    db.flush()
    db.expire(user, ["subjects"])
    summary = planner.generate(db, user)
    db.commit()
    return {"created": summary.created, "planned_minutes": summary.planned_minutes, "warnings": summary.warnings}
