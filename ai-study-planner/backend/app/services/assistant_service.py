"""Natural-language planning.

Pipeline:  text -> (rule parser | AI fallback) -> list of *structured actions* -> pydantic validation -> preview
           -> user confirms -> server re-validates -> executor applies actions with ordinary planner code.
The model never touches the database: it can only propose actions from the whitelist below.
"""
import re
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from types import SimpleNamespace
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from .. import models as m
from ..timeutil import hhmm, local_now, parse_hhmm
from . import ai_service
from . import planner_service as planner
from . import priority_service as ps

Date = date
TIME = r"^([01]\d|2[0-3]):[0-5]\d$"


# ------------------------------------------------------------------ action schema (the whitelist)
class AddTask(BaseModel):
    type: Literal["add_task"]
    subject: Optional[str] = Field(None, max_length=80)
    topic: Optional[str] = Field(None, max_length=120)
    date: Date
    start_time: Optional[str] = Field(None, pattern=TIME)
    duration_minutes: int = Field(45, ge=10, le=240)
    task_type: Literal["study", "revision", "practice"] = "study"
    notes: str = Field("", max_length=300)


class MoveTask(BaseModel):
    type: Literal["move_task"]
    task_id: Optional[int] = None
    subject: Optional[str] = Field(None, max_length=80)
    topic: Optional[str] = Field(None, max_length=120)
    from_date: Optional[Date] = None
    to_date: Date
    to_time: Optional[str] = Field(None, pattern=TIME)


class BlockDay(BaseModel):
    type: Literal["block_day"]
    date: Date


class SetDailyLimit(BaseModel):
    type: Literal["set_daily_limit"]
    minutes: int = Field(ge=0, le=600)
    start_date: Optional[Date] = None
    days: int = Field(1, ge=1, le=60)


class SetDailyMinutes(BaseModel):
    type: Literal["set_daily_minutes"]
    minutes: int = Field(ge=30, le=600)


class FocusSubject(BaseModel):
    type: Literal["focus_subject"]
    subject: str = Field(max_length=80)
    days: int = Field(7, ge=1, le=30)


class AddRevision(BaseModel):
    type: Literal["add_revision"]
    subject: Optional[str] = Field(None, max_length=80)
    topic: Optional[str] = Field(None, max_length=120)
    date: Date
    start_time: Optional[str] = Field(None, pattern=TIME)
    duration_minutes: int = Field(30, ge=10, le=90)


class Rebalance(BaseModel):
    type: Literal["rebalance"]
    date: Date


class ShiftMinutes(BaseModel):
    type: Literal["shift_minutes"]
    from_subject_id: int
    to_subject_id: int
    minutes: int = Field(30, ge=10, le=120)


class EaseDay(BaseModel):
    type: Literal["ease_day"]
    date: Date
    factor: float = Field(0.7, ge=0.3, le=0.95)


class AddRevisions(BaseModel):
    type: Literal["add_revisions"]
    topic_id: int
    count: int = Field(3, ge=1, le=5)


class Replan(BaseModel):
    type: Literal["replan"]


Action = Annotated[Union[AddTask, MoveTask, BlockDay, SetDailyLimit, SetDailyMinutes, FocusSubject, AddRevision, Rebalance,
                         ShiftMinutes, EaseDay, AddRevisions, Replan], Field(discriminator="type")]
ACTIONS = TypeAdapter(list[Action])
ACTION_ONE = TypeAdapter(Action)
AI_ALLOWED = {"add_task", "move_task", "block_day", "set_daily_limit", "focus_subject", "add_revision", "replan"}


def validate_actions(raw: list) -> tuple[list, list[str]]:
    ok, errors = [], []
    for item in raw[:8]:
        try:
            ok.append(ACTION_ONE.validate_python(item))
        except ValidationError as exc:
            errors.append(f"Skipped an invalid action: {exc.errors()[0]['msg']}")
    return ok, errors


# ------------------------------------------------------------------ name resolution
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


def _acronym(s: str) -> str:
    return "".join(w[0] for w in _norm(s).split() if w)


def _best(name: str, items: list[tuple[str, object]]):
    n = _norm(name)
    if not n:
        return None
    for key, obj in items:
        if _norm(key) == n or _acronym(key) == n.replace(" ", ""):
            return obj
    for key, obj in items:
        if _norm(key).startswith(n) or n in _norm(key):
            return obj
    scored = sorted(((SequenceMatcher(None, n, _norm(k)).ratio(), o) for k, o in items), key=lambda x: -x[0])
    return scored[0][1] if scored and scored[0][0] >= 0.72 else None


def resolve_subject(user: m.User, name: str | None) -> m.Subject | None:
    return _best(name, [(s.name, s) for s in user.subjects]) if name else None


def resolve_topic(user: m.User, name: str | None, subject: m.Subject | None = None) -> m.Topic | None:
    if not name:
        return None
    pool = [(t.name, t) for s in user.subjects if subject is None or s.id == subject.id for t in s.topics]
    return _best(name, pool)


def weakest_topic(user: m.User, subject: m.Subject | None = None, today: date | None = None) -> m.Topic | None:
    today = today or date.today()
    pool = []
    for s in user.subjects:
        if subject and s.id != subject.id:
            continue
        exam = planner.subject_exam(s, today)
        for t in s.topics:
            pool.append((0 if exam else 1, t.mastery, t))
    return min(pool, key=lambda x: (x[0], x[1]))[2] if pool else None


# ------------------------------------------------------------------ language helpers
WEEKDAYS = {"monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2, "thursday": 3, "thu": 3,
            "thur": 3, "thurs": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6}
MONTHS = {k: i + 1 for i, k in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def parse_date(text: str, today: date) -> date | None:
    t = text.lower()
    if re.search(r"\bday after tomorrow\b", t):
        return today + timedelta(days=2)
    if re.search(r"\b(tomorrow|tmrw|tmr)\b", t):
        return today + timedelta(days=1)
    if re.search(r"\b(today|tonight|this (morning|afternoon|evening))\b", t):
        return today
    mi = re.search(r"\bin (\d{1,2}) days?\b", t)
    if mi and "exam" not in t[:mi.start()][-12:]:
        return today + timedelta(days=int(mi.group(1)))
    iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", t)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None
    md = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", t) or None
    dm = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?\b", t)
    try:
        if md:
            d = date(today.year, MONTHS[md.group(2)], int(md.group(1)))
        elif dm:
            d = date(today.year, MONTHS[dm.group(1)], int(dm.group(2)))
        else:
            d = None
        if d:
            return d if d >= today else d.replace(year=today.year + 1)
    except ValueError:
        return None
    wd = re.search(r"\b(?:(next|this)\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tues?|wed|thu(?:rs?)?|fri|sat|sun)\b", t)
    if wd:
        target = WEEKDAYS[wd.group(2)]
        delta = (target - today.weekday()) % 7 or 7
        if wd.group(1) == "next" and delta <= 7 - today.weekday() - 1 + 0:
            pass
        return today + timedelta(days=delta)
    return None


def parse_time(text: str) -> int | None:
    t = text.lower()
    mt = re.search(r"\b(?:at\s*)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", t) or re.search(r"\bat\s*(\d{1,2})(?::(\d{2}))?\s*()\b", t)
    if mt:
        h, mnt, ap = int(mt.group(1)), int(mt.group(2) or 0), mt.group(3)
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        if not ap and h < 7:
            h += 12
        if h < 24 and mnt < 60:
            return h * 60 + mnt
    if re.search(r"\btonight\b", t):
        return 19 * 60 + 30
    for word, minute in (("morning", 9 * 60), ("afternoon", 14 * 60), ("evening", 18 * 60), ("night", 20 * 60 + 30)):
        if word in t:
            return minute
    return None


def parse_duration(text: str) -> int | None:
    t = text.lower()
    if re.search(r"\bhalf an? hour\b", t):
        return 30
    h = re.search(r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b", t)
    mn = re.search(r"(\d{1,3})\s*(?:minutes?|mins?|m)\b", t)
    if h and mn:
        return int(float(h.group(1)) * 60 + int(mn.group(1)))
    if h:
        return int(float(h.group(1)) * 60)
    if mn:
        return int(mn.group(1))
    if re.search(r"\ban hour\b", t):
        return 60
    return None


def _find_names(user: m.User, text: str) -> tuple[m.Subject | None, m.Topic | None]:
    n = f" {_norm(text)} "
    topic = subj = None
    topics = sorted(((t.name, t, s) for s in user.subjects for t in s.topics), key=lambda x: -len(x[0]))
    for name, t, s in topics:
        if f" {_norm(name)} " in n:
            topic, subj = t, s
            break
    if not subj:
        for s in sorted(user.subjects, key=lambda s: -len(s.name)):
            if f" {_norm(s.name)} " in n or f" {_acronym(s.name).lower()} " in n:
                subj = s
                break
    return subj, topic


# ------------------------------------------------------------------ rule-based interpreter
def interpret_rules(db: Session, user: m.User, text: str, today: date) -> dict | None:
    t = text.strip()
    low = t.lower()
    prefs = user.preferences
    d = parse_date(low, today)
    dur = parse_duration(low)
    when = parse_time(low)
    subj, topic = _find_names(user, low)

    if re.search(r"\b(can'?t|cannot|can not|won'?t be able to|unable to|not able to|no time to)\b.*\b(study|revise)\b|\b(no study|day off)\b", low):
        if d is None:
            return {"understood": False, "reply": "Which day can't you study? For example: “I can't study tomorrow.”", "actions": []}
        return {"understood": True, "reply": f"Okay — I'll mark {d:%A %d %b} as a no-study day and spread its sessions across your other days.",
                "actions": [{"type": "block_day", "date": d.isoformat()}]}

    m_exam = re.search(r"exam[^.]*?in\s+(\d{1,2})\s+days?", low)
    m_hours = re.search(r"(?:only\s+)?(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\s*(?:per|a|each|/)\s*day", low)
    if m_exam and m_hours:
        days = int(m_exam.group(1))
        minutes = int(float(m_hours.group(1)) * 60)
        return {"understood": True, "reply": f"With {days} days to go and {minutes // 60}h{minutes % 60 or ''} a day, I'll cap your daily load and "
                                             "re-prioritise so the weakest, most urgent topics come first.",
                "actions": [{"type": "set_daily_limit", "minutes": minutes, "start_date": today.isoformat(), "days": min(days, 60)}]}

    if re.search(r"\b(make|keep)\b.*\b(plan|schedule|week|today)\b.*\b(easier|lighter|relaxed)\b|too much|overwhelm|reduce (my )?(workload|load)|lighter", low):
        base = min(prefs.max_daily_minutes, max(planner.day_capacity(prefs, today), 60))
        minutes = max(45, int(base * 0.7) // 15 * 15)
        return {"understood": True, "reply": f"I'll lighten the next 7 days to about {minutes // 60}h{minutes % 60 or ''} per day and replan around it.",
                "actions": [{"type": "set_daily_limit", "minutes": minutes, "start_date": today.isoformat(), "days": 7}]}

    mf = re.search(r"\bfocus (?:more )?on\b", low)
    if mf and subj:
        days = 7 if "week" in low else (int(re.search(r"(\d+)\s*days?", low).group(1)) if re.search(r"(\d+)\s*days?", low) else 7)
        return {"understood": True, "reply": f"I'll weight {subj.name} higher for the next {days} days.",
                "actions": [{"type": "focus_subject", "subject": subj.name, "days": min(days, 30)}]}

    if re.search(r"\b(move|shift|reschedule|push)\b", low):
        if d is None:
            return {"understood": False, "reply": "Where should I move it? For example: “Move Python to Saturday.”", "actions": []}
        if not (subj or topic):
            return {"understood": False, "reply": "Which subject or topic should I move? I didn't recognise a name in that message.", "actions": []}
        act = {"type": "move_task", "to_date": d.isoformat()}
        if topic:
            act["topic"] = topic.name
        if subj:
            act["subject"] = subj.name
        if when is not None and re.search(r"\bat\b|\b(am|pm)\b", low):
            act["to_time"] = hhmm(when)
        return {"understood": True, "reply": f"I'll move the next {(topic or subj).name} session to {d:%A %d %b}.", "actions": [act]}

    if "revis" in low and (dur or d):
        day = d or today
        act = {"type": "add_revision", "date": day.isoformat(), "duration_minutes": min(max(dur or 30, 10), 90)}
        if subj:
            act["subject"] = subj.name
        if topic:
            act["topic"] = topic.name
        if when is not None:
            act["start_time"] = hhmm(when)
        who = topic.name if topic else (subj.name if subj else "your weakest topic")
        return {"understood": True, "reply": f"I'll add a {act['duration_minutes']}-minute revision session on {who} for {day:%A %d %b}.", "actions": [act]}

    if re.search(r"\b(study|learn|practi[sc]e|revise|review|read|schedule|add|work on)\b", low) and (subj or topic):
        day = d or today
        act = {"type": "add_task", "date": day.isoformat(), "duration_minutes": min(max(dur or 45, 10), 240)}
        if topic:
            act["topic"] = topic.name
        if subj:
            act["subject"] = subj.name
        if when is not None:
            act["start_time"] = hhmm(when)
        return {"understood": True, "reply": f"I'll schedule {act['duration_minutes']} minutes of {(topic or subj).name} on {day:%A %d %b}"
                                             f"{' at ' + act['start_time'] if 'start_time' in act else ''}.", "actions": [act]}
    return None


EXAMPLES = ["Study Trees tomorrow for 1 hour", "Move Python to Saturday", "Give me 30 minutes of revision tonight",
            "I cannot study tomorrow", "I want to focus on Data Structures this week", "Make my plan easier"]


def interpret(db: Session, user: m.User, text: str, now: datetime | None = None, allow_ai: bool = True) -> dict:
    now = now or local_now(user.preferences.timezone)
    today = now.date()
    result = interpret_rules(db, user, text, today)
    source = "rules"
    ai_note = None
    if result is None:
        if allow_ai and ai_service.is_enabled():
            try:
                result = _interpret_ai(db, user, text, today)
                source = "ai"
            except ai_service.AIUnavailable:
                ai_note = ai_service.UNAVAILABLE_MESSAGE
        if result is None:
            reply = "I couldn't turn that into a change to your plan. " + (ai_note + " " if ai_note else "") + \
                    "Try something like: " + "; ".join(f"“{e}”" for e in EXAMPLES[:3]) + "."
            return {"understood": False, "reply": reply, "actions": [], "descriptions": [], "errors": [], "source": "rules",
                    "ai_available": ai_note is None and ai_service.is_enabled()}
    actions, errors = validate_actions(result.get("actions", []))
    errors += [e for a in actions if (e := check_action(db, user, a, today))]
    ok_actions = [a for a in actions if not check_action(db, user, a, today)]
    return {"understood": bool(ok_actions) and result.get("understood", True), "reply": result.get("reply", ""),
            "actions": [a.model_dump(mode="json") for a in ok_actions], "descriptions": [describe(db, user, a) for a in ok_actions],
            "errors": errors, "source": source, "ai_available": ai_service.is_enabled()}


AI_SYSTEM = (
    "You convert a student's request into JSON actions for a study planner. Reply with JSON only: "
    '{"reply": "<one friendly sentence>", "actions": [...]}. Allowed action objects (dates are YYYY-MM-DD, times HH:MM 24h):\n'
    '{"type":"add_task","subject":str,"topic":str|null,"date":d,"start_time":t|null,"duration_minutes":10-240,"task_type":"study|revision|practice"}\n'
    '{"type":"move_task","subject":str|null,"topic":str|null,"to_date":d,"to_time":t|null}\n'
    '{"type":"block_day","date":d}\n{"type":"set_daily_limit","minutes":0-600,"start_date":d,"days":1-60}\n'
    '{"type":"focus_subject","subject":str,"days":1-30}\n{"type":"add_revision","subject":str|null,"topic":str|null,"date":d,"duration_minutes":10-90}\n'
    '{"type":"replan"}\nUse only subject/topic names from the provided lists. If the request cannot be expressed, return an empty actions list.')


def _interpret_ai(db: Session, user: m.User, text: str, today: date) -> dict:
    ctx = "; ".join(f"{s.name}: {', '.join(t.name for t in s.topics[:12])}" for s in user.subjects[:10])
    prompt = f"Today is {today:%A %Y-%m-%d}.\nSubjects/topics: {ctx}\nRequest: {text[:300]}"
    out, _ = ai_service.complete(db, user, system=AI_SYSTEM, prompt=prompt, max_tokens=450)
    try:
        data = ai_service.extract_json(out)
    except (ValueError, TypeError):
        raise ai_service.AIUnavailable("unparseable response")
    acts = [a for a in data.get("actions", []) if isinstance(a, dict) and a.get("type") in AI_ALLOWED]
    return {"understood": bool(acts), "reply": str(data.get("reply", ""))[:300], "actions": acts}


# ------------------------------------------------------------------ validation + description
def check_action(db: Session, user: m.User, a, today: date) -> str | None:
    if isinstance(a, (AddTask, AddRevision)):
        if a.date < today:
            return "That date is in the past."
        subj = resolve_subject(user, a.subject)
        topic = resolve_topic(user, a.topic, subj)
        if isinstance(a, AddTask) and not (subj or topic):
            return f"I couldn't find “{a.topic or a.subject}” in your subjects."
        if isinstance(a, AddRevision) and (a.subject or a.topic) and not (subj or topic):
            return f"I couldn't find “{a.topic or a.subject}” in your subjects."
    if isinstance(a, MoveTask):
        if a.to_date < today:
            return "I can't move a session into the past."
        if not (a.task_id or resolve_subject(user, a.subject) or resolve_topic(user, a.topic)):
            return "I couldn't tell which session to move."
        if _find_task_to_move(db, user, a, today) is None:
            return f"I couldn't find an upcoming {a.topic or a.subject or 'session'} to move."
    if isinstance(a, BlockDay) and a.date < today:
        return "That day has already passed."
    if isinstance(a, FocusSubject) and not resolve_subject(user, a.subject):
        return f"I couldn't find the subject “{a.subject}”."
    if isinstance(a, ShiftMinutes):
        ids = {s.id for s in user.subjects}
        if a.from_subject_id not in ids or a.to_subject_id not in ids:
            return "That subject no longer exists."
    if isinstance(a, AddRevisions):
        if not any(t.id == a.topic_id for s in user.subjects for t in s.topics):
            return "That topic no longer exists."
    return None


def describe(db: Session, user: m.User, a) -> str:
    if isinstance(a, AddTask):
        n = (resolve_topic(user, a.topic, resolve_subject(user, a.subject)) or resolve_subject(user, a.subject))
        return f"Add {a.duration_minutes} min of {n.name if n else a.topic or a.subject} on {a.date:%a %d %b}" + (f" at {a.start_time}" if a.start_time else "")
    if isinstance(a, AddRevision):
        return f"Add {a.duration_minutes} min of revision on {a.date:%a %d %b}" + (f" at {a.start_time}" if a.start_time else "")
    if isinstance(a, MoveTask):
        return f"Move {a.topic or a.subject or 'session'} to {a.to_date:%a %d %b}" + (f" at {a.to_time}" if a.to_time else "")
    if isinstance(a, BlockDay):
        return f"Mark {a.date:%a %d %b} as a no-study day and replan"
    if isinstance(a, SetDailyLimit):
        return f"Limit study to {a.minutes // 60}h{a.minutes % 60 or ''} per day for {a.days} day(s) and replan"
    if isinstance(a, SetDailyMinutes):
        return f"Set your weekday study time to {a.minutes // 60}h{a.minutes % 60 or ''} and replan"
    if isinstance(a, FocusSubject):
        return f"Prioritise {a.subject} for {a.days} days"
    if isinstance(a, Rebalance):
        return f"Rebalance {a.date:%a %d %b}"
    if isinstance(a, ShiftMinutes):
        f_, t_ = db.get(m.Subject, a.from_subject_id), db.get(m.Subject, a.to_subject_id)
        return f"Move {a.minutes} min from {f_.name if f_ else '?'} to {t_.name if t_ else '?'}"
    if isinstance(a, EaseDay):
        return f"Lighten {a.date:%a %d %b} to {int(a.factor * 100)}% of its load"
    if isinstance(a, AddRevisions):
        t_ = db.get(m.Topic, a.topic_id)
        return f"Schedule {a.count} revision sessions for {t_.name if t_ else 'topic'} before the exam"
    return "Rebuild the plan from today"


# ------------------------------------------------------------------ executor
def _find_task_to_move(db: Session, user: m.User, a: MoveTask, today: date) -> m.StudyTask | None:
    q = db.query(m.StudyTask).filter(m.StudyTask.user_id == user.id, m.StudyTask.status == "pending", m.StudyTask.date >= today)
    if a.task_id:
        return q.filter(m.StudyTask.id == a.task_id).first()
    subj = resolve_subject(user, a.subject)
    topic = resolve_topic(user, a.topic, subj)
    if topic:
        q = q.filter(m.StudyTask.topic_id == topic.id)
    elif subj:
        q = q.filter(m.StudyTask.subject_id == subj.id)
    else:
        return None
    if a.from_date:
        q = q.filter(m.StudyTask.date == a.from_date)
    return q.order_by(m.StudyTask.date, m.StudyTask.start_minute).first()


def _priority(user: m.User, topic: m.Topic, subj: m.Subject, day: date) -> ps.Priority:
    return ps.compute(mastery=topic.mastery, topic_difficulty=topic.difficulty, subject_importance=subj.importance,
                      target_marks=subj.target_marks, miss_count=topic.miss_count, last_studied=topic.last_studied,
                      exam_date=planner.subject_exam(subj, day), on_date=day)


def _create_task(db: Session, user: m.User, topic: m.Topic, subj: m.Subject, day: date, minute: int | None, duration: int,
                 ttype: str, notes: str, now: datetime, origin: str = "assistant", reason: str = "") -> tuple[m.StudyTask | None, str]:
    prefs = user.preferences
    if day.isoformat() in (prefs.blocked_dates or []):
        return None, f"{day:%a %d %b} is marked as a no-study day."
    slot = planner.find_free_slot(db, user, day, duration, preferred=minute, respect_capacity=False, now=now)
    if slot is None and minute is not None:
        busy = [(t.start_minute, t.start_minute + t.duration_minutes) for t in db.query(m.StudyTask).filter(
            m.StudyTask.user_id == user.id, m.StudyTask.date == day, m.StudyTask.status.in_(planner.ACTIVE))]
        if not any(minute < be and minute + duration > bs for bs, be in busy) and (day > now.date() or minute > now.hour * 60 + now.minute):
            slot = minute
    if slot is None:
        return None, f"There's no free {duration}-minute slot on {day:%a %d %b}."
    p = _priority(user, topic, subj, day)
    t = m.StudyTask(user_id=user.id, subject_id=subj.id, topic_id=topic.id, title=topic.name, task_type=ttype, date=day,
                    start_minute=slot, duration_minutes=duration, priority=p.level, priority_score=p.score,
                    difficulty=topic.difficulty, origin=origin, locked=True, notes=notes, reason=reason[:240])
    db.add(t)
    db.flush()
    return t, ""


def execute(db: Session, user: m.User, actions: list, now: datetime | None = None) -> list[dict]:
    prefs = user.preferences
    now = now or local_now(prefs.timezone)
    today = now.date()
    results: list[dict] = []
    need_replan = False
    displaced: list = []

    def ok(a, msg):
        results.append({"type": a.type, "ok": True, "message": msg})

    def fail(a, msg):
        results.append({"type": a.type, "ok": False, "message": msg})

    for a in actions:
        err = check_action(db, user, a, today)
        if err:
            fail(a, err)
            continue
        if isinstance(a, (AddTask, AddRevision)):
            subj = resolve_subject(user, a.subject)
            topic = resolve_topic(user, a.topic, subj)
            if topic and not subj:
                subj = topic.subject
            if not topic:
                topic = weakest_topic(user, subj, today)
                subj = subj or (topic.subject if topic else None)
            if not topic or not subj:
                fail(a, "Add a subject with topics first.")
                continue
            ttype = "revision" if isinstance(a, AddRevision) else a.task_type
            minute = parse_hhmm(a.start_time) if a.start_time else None
            reason = "Added by you via the planning assistant" if isinstance(a, AddTask) else f"Revision added for weak topic · {topic.mastery}% mastery"
            t, why = _create_task(db, user, topic, subj, a.date, minute, a.duration_minutes, ttype, getattr(a, "notes", ""), now, reason=reason)
            if t:
                ok(a, f"Added {t.duration_minutes} min of {topic.name} on {t.date:%a %d %b} at {hhmm(t.start_minute)}.")
            else:
                fail(a, why)
        elif isinstance(a, MoveTask):
            t = _find_task_to_move(db, user, a, today)
            if not t:
                fail(a, "No upcoming session found to move.")
                continue
            minute = parse_hhmm(a.to_time) if a.to_time else None
            old = (t.date, t.start_minute)
            if a.to_date.isoformat() in (prefs.blocked_dates or []):
                fail(a, f"{a.to_date:%a %d %b} is a no-study day.")
                continue
            slot = planner.find_free_slot(db, user, a.to_date, t.duration_minutes, preferred=minute, respect_capacity=False, now=now)
            if slot is None:
                fail(a, f"No free slot on {a.to_date:%a %d %b}.")
                continue
            t.moved_from, t.date, t.start_minute, t.locked = old[0], a.to_date, slot, True
            t.reschedule_count += 1
            t.reason = f"Moved by you from {old[0]:%a %d %b}"
            ok(a, f"Moved {t.title} to {t.date:%a %d %b} at {hhmm(slot)}.")
        elif isinstance(a, BlockDay):
            prefs.blocked_dates = sorted(set((prefs.blocked_dates or []) + [a.date.isoformat()]))
            day_tasks = db.query(m.StudyTask).filter(m.StudyTask.user_id == user.id, m.StudyTask.date == a.date,
                                                     m.StudyTask.status == "pending").all()
            moved_locked = 0
            for t in day_tasks:
                if t.origin == "generated" and not t.locked:
                    displaced.append(SimpleNamespace(topic_id=t.topic_id, title=t.title, date=t.date, start_minute=t.start_minute,
                                                     reschedule_count=t.reschedule_count))
                    continue
                for off in range(1, 8):
                    d2 = a.date + timedelta(days=off)
                    if d2 in [x for x in []] or d2.isoformat() in (prefs.blocked_dates or []):
                        continue
                    s = planner.find_free_slot(db, user, d2, t.duration_minutes, now=now)
                    if s is not None:
                        t.moved_from, t.date, t.start_minute = a.date, d2, s
                        t.reschedule_count += 1
                        moved_locked += 1
                        break
            need_replan = True
            ok(a, f"{a.date:%A %d %b} is now a no-study day; I rebuilt the plan around it.")
        elif isinstance(a, SetDailyLimit):
            start = a.start_date or today
            ov = dict(prefs.day_overrides or {})
            for i in range(a.days):
                ov[(start + timedelta(days=i)).isoformat()] = a.minutes
            prefs.day_overrides = ov
            need_replan = True
            ok(a, f"Daily limit set to {a.minutes // 60}h{a.minutes % 60 or ''} for {a.days} day(s); plan rebuilt.")
        elif isinstance(a, SetDailyMinutes):
            prefs.daily_minutes = [a.minutes] * 7
            prefs.max_daily_minutes = max(prefs.max_daily_minutes, a.minutes)
            need_replan = True
            ok(a, f"Study time set to {a.minutes // 60}h{a.minutes % 60 or ''} per day; plan rebuilt.")
        elif isinstance(a, FocusSubject):
            subj = resolve_subject(user, a.subject)
            boosts = dict(prefs.focus_boosts or {})
            boosts[str(subj.id)] = (today + timedelta(days=a.days)).isoformat()
            prefs.focus_boosts = boosts
            need_replan = True
            ok(a, f"{subj.name} is prioritised until {today + timedelta(days=a.days):%d %b}; plan rebuilt.")
        elif isinstance(a, Rebalance):
            r = planner.rebalance_day(db, user, a.date, now)
            ok(a, f"Moved {r['moved']} session(s) off {a.date:%a %d %b}." + (f" {r['unmovable']} could not be moved." if r["unmovable"] else ""))
        elif isinstance(a, EaseDay):
            used = planner.day_used_minutes(db, user.id, a.date)
            target = max(30, int(max(used, planner.day_capacity(prefs, a.date)) * a.factor) // 5 * 5)
            ov = dict(prefs.day_overrides or {})
            ov[a.date.isoformat()] = target
            prefs.day_overrides = ov
            need_replan = True
            ok(a, f"{a.date:%a %d %b} lightened to {target} min; the remainder is spread over later days.")
        elif isinstance(a, ShiftMinutes):
            msg = _shift_minutes(db, user, a, now)
            (ok if msg[0] else fail)(a, msg[1])
        elif isinstance(a, AddRevisions):
            topic = db.get(m.Topic, a.topic_id)
            subj = topic.subject
            exam = planner.subject_exam(subj, today)
            made = 0
            for off in (1, 3, 6, 10, 14):
                if made >= a.count:
                    break
                d = (exam - timedelta(days=off)) if exam else today + timedelta(days=off)
                if d < today:
                    continue
                t, _ = _create_task(db, user, topic, subj, d, None, 25, "revision", "", now,
                                    reason=f"Revision for weak topic · {topic.mastery}% mastery")
                made += 1 if t else 0
            (ok if made else fail)(a, f"Scheduled {made} revision session(s) for {topic.name}." if made else "No free days before the exam.")
        elif isinstance(a, Replan):
            need_replan = True
            ok(a, "Plan rebuilt from today.")

    if need_replan:
        planner.generate(db, user, now)
        if displaced:
            planner.link_moved(db, user, displaced, now)
    db.flush()
    return results


def _shift_minutes(db: Session, user: m.User, a: ShiftMinutes, now: datetime) -> tuple[bool, str]:
    today = now.date()
    src = (db.query(m.StudyTask).filter(m.StudyTask.user_id == user.id, m.StudyTask.subject_id == a.from_subject_id,
                                        m.StudyTask.status == "pending", m.StudyTask.date >= today)
           .order_by(m.StudyTask.date, m.StudyTask.start_minute).all())
    src = [t for t in src if t.duration_minutes >= a.minutes + 15]
    dst_subj = db.get(m.Subject, a.to_subject_id)
    if not src:
        return False, "No upcoming session is long enough to shorten."
    donor = src[0]
    topic = weakest_topic(user, dst_subj, today)
    if not topic:
        return False, "The target subject has no topics."
    donor.duration_minutes -= a.minutes
    donor.locked = True
    donor.reason = (donor.reason + f" · shortened by {a.minutes} min")[:240]
    for d in (donor.date, donor.date + timedelta(days=1)):
        if d < today:
            continue
        t, _ = _create_task(db, user, topic, dst_subj, d, None, a.minutes, "study", "", now, origin="assistant",
                            reason=f"Extra time for {dst_subj.name}: exam is closer")
        if t:
            return True, f"Moved {a.minutes} min from {donor.subject.name} to {topic.name} ({dst_subj.name}) on {t.date:%a %d %b}."
    donor.duration_minutes += a.minutes
    return False, "No free slot to place the extra time."
