"""Scheduling engine. Pure algorithms, no AI.

generate(): rebuilds every *unlocked, pending, generated* task from today onwards.
  1. Per-topic need (minutes) from mastery gap, difficulty and target marks, minus time already booked by fixed tasks.
  2. Pre-exam revision slots are reserved (1-3 per topic depending on mastery) on the last days before each exam.
  3. Day by day: capacity = weekday hours (or override) capped by max-daily; a *pacing target* spreads the remaining
     need evenly (x1.6 buffer, so work is front-loaded) but never below what each exam needs per day to still be finished in time.
  4. Blocks are chosen by priority(day) x deadline-pressure, penalised when the same subject/topic was just scheduled
     (subject variation), and placed into free slots inside the student's preferred windows with breaks between blocks.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from .. import models as m
from ..timeutil import ceil5, hhmm, local_now
from . import priority_service as ps

PREF_WINDOWS = {"morning": (8 * 60, 12 * 60), "afternoon": (13 * 60 + 30, 17 * 60),
                "evening": (18 * 60, 21 * 60 + 30), "night": (21 * 60 + 30, 23 * 60 + 30)}
SOFT_WINDOW_MINUTES = 110      # try not to put more than this in one window while another window is free
OVERDUE_GRACE = 15
MAX_HORIZON_DAYS = 120
ACTIVE = ("pending", "in_progress", "completed")
BLOCK_BY_DIFFICULTY = {1: 30, 2: 35, 3: 40, 4: 45, 5: 50}


# ---------------------------------------------------------------- capacity & windows
def windows_for(prefs: m.StudyPreferences) -> list[tuple[int, int]]:
    out = []
    for key in prefs.preferred_times or ["morning", "evening"]:
        w = PREF_WINDOWS.get(key)
        if not w:
            continue
        s, e = max(w[0], prefs.wake_time), min(w[1], prefs.sleep_start)
        if e - s >= 15:
            out.append((s, e))
    out.sort()
    merged: list[tuple[int, int]] = []
    for s, e in out:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged or [(9 * 60, 12 * 60), (18 * 60, 21 * 60)]


def day_capacity(prefs: m.StudyPreferences, d: date) -> int:
    iso = d.isoformat()
    if iso in (prefs.blocked_dates or []):
        return 0
    override = (prefs.day_overrides or {}).get(iso)
    base = override if override is not None else prefs.daily_minutes[d.weekday()]
    return max(0, min(int(base), prefs.max_daily_minutes))


class DayAllocator:
    """Finds free start times inside the preferred windows with breaks between blocks."""

    def __init__(self, windows, busy, gap: int, earliest: int = 0):
        self.windows, self.busy, self.gap, self.earliest = windows, list(busy), gap, earliest

    def _fits(self, s: int, e: int) -> bool:
        return all(not (s < be + self.gap and e + self.gap > bs) for bs, be in self.busy)

    def _chain_minutes(self, s: int) -> int:
        """Minutes of back-to-back study (breaks <= gap+4) directly before start `s`."""
        total, edge = 0, s
        for bs, be in sorted(self.busy, key=lambda b: -b[1]):
            if be <= edge and edge - be <= self.gap + 4:
                total += be - bs
                edge = bs
        return total

    def _used_in(self, ws: int, we: int) -> int:
        return sum(max(0, min(be, we) - max(bs, ws)) for bs, be in self.busy)

    def find(self, duration: int, earliest: int | None = None) -> int | None:
        # pass 1 spreads work across windows (morning + evening); pass 2 fills whatever is left
        for soft in (True, False):
            for i, (ws, we) in enumerate(self.windows):
                if soft and i < len(self.windows) - 1 and self._used_in(ws, we) + duration > SOFT_WINDOW_MINUTES:
                    continue
                s = ceil5(max(ws, earliest or 0, self.earliest))
                while s + duration <= we:
                    if self._fits(s, s + duration) and self._chain_minutes(s) + duration <= 105:
                        return s
                    s += 5
        return None

    def add(self, start: int, duration: int) -> None:
        self.busy.append((start, start + duration))


def _earliest_for(day: date, now: datetime) -> int:
    return ceil5(now.hour * 60 + now.minute + 5) if day == now.date() else 0


# ---------------------------------------------------------------- data helpers
def subject_exam(subject: m.Subject, from_day: date) -> date | None:
    upcoming = [e.exam_date for e in subject.exams if e.exam_date >= from_day]
    return min(upcoming) if upcoming else None


def fixed_tasks_from(db: Session, user_id: int, start: date) -> list[m.StudyTask]:
    return (db.query(m.StudyTask).filter(m.StudyTask.user_id == user_id, m.StudyTask.date >= start,
                                         m.StudyTask.status.in_(ACTIVE)).all())


def build_allocator(db: Session, user: m.User, day: date, now: datetime, tasks: list[m.StudyTask] | None = None) -> DayAllocator:
    prefs = user.preferences
    if tasks is None:
        tasks = db.query(m.StudyTask).filter(m.StudyTask.user_id == user.id, m.StudyTask.date == day,
                                             m.StudyTask.status.in_(ACTIVE)).all()
    busy = [(t.start_minute, t.start_minute + t.duration_minutes) for t in tasks if t.date == day]
    return DayAllocator(windows_for(prefs), busy, prefs.break_minutes, _earliest_for(day, now))


def day_used_minutes(db: Session, user_id: int, day: date) -> int:
    rows = db.query(m.StudyTask.duration_minutes).filter(m.StudyTask.user_id == user_id, m.StudyTask.date == day,
                                                         m.StudyTask.status.in_(ACTIVE)).all()
    return sum(r[0] for r in rows)


def find_free_slot(db: Session, user: m.User, day: date, duration: int, *, preferred: int | None = None,
                   respect_capacity: bool = True, now: datetime | None = None) -> int | None:
    now = now or local_now(user.preferences.timezone)
    if day < now.date():
        return None
    if respect_capacity and day_used_minutes(db, user.id, day) + duration > max(day_capacity(user.preferences, day), 0):
        return None
    alloc = build_allocator(db, user, day, now)
    if preferred is not None and day >= now.date():
        s = alloc.find(duration, earliest=preferred)
        if s is not None:
            return s
    return alloc.find(duration)


def revisions_wanted(mastery: int) -> int:
    return 3 if mastery < 40 else 2 if mastery < 65 else 1


# ---------------------------------------------------------------- generation
@dataclass
class TState:
    topic: m.Topic
    subject: m.Subject
    exam: date
    has_exam: bool
    need_left: int
    placed_today: int = 0


@dataclass
class PlanSummary:
    created: int = 0
    planned_minutes: int = 0
    warnings: list = field(default_factory=list)
    horizon_end: date | None = None


def generate(db: Session, user: m.User, now: datetime | None = None) -> PlanSummary:
    prefs = user.preferences
    now = now or local_now(prefs.timezone)
    today = now.date()
    summary = PlanSummary()

    # 1) drop the part of the plan that can be recomputed; remember "moved from" badges
    old = (db.query(m.StudyTask).filter(m.StudyTask.user_id == user.id, m.StudyTask.date >= today,
                                        m.StudyTask.status == "pending", m.StudyTask.locked.is_(False),
                                        m.StudyTask.origin == "generated").all())
    carry: dict[int, tuple[date, int]] = {}
    for t in old:
        if t.moved_from and t.topic_id:
            carry[t.topic_id] = (t.moved_from, t.reschedule_count)
        db.delete(t)
    db.flush()

    fixed = fixed_tasks_from(db, user.id, today)
    fixed_by_day: dict[date, list[m.StudyTask]] = {}
    for t in fixed:
        fixed_by_day.setdefault(t.date, []).append(t)

    # 2) per-topic state
    states: list[TState] = []
    for subj in user.subjects:
        exam = subject_exam(subj, today)
        has_exam = exam is not None
        eff = exam or (today + timedelta(days=30))
        if has_exam and exam <= today:
            continue                      # exam is today: nothing new to learn
        boost_until = (prefs.focus_boosts or {}).get(str(subj.id))
        for tp in subj.topics:
            need = ps.minutes_needed(tp.mastery, tp.difficulty, subj.target_marks)
            booked = sum(t.duration_minutes for t in fixed
                         if t.topic_id == tp.id and t.status == "pending" and t.task_type != "revision" and t.date < eff)
            need = max(0, need - booked)
            if need > 0:
                states.append(TState(tp, subj, eff, has_exam, ceil5(need)))

    end_day = min(max([s.exam for s in states] + [today]) - timedelta(days=1), today + timedelta(days=MAX_HORIZON_DAYS))
    summary.horizon_end = end_day
    all_subjects = {s.id: s for s in user.subjects}

    # 3) reserve pre-exam revisions
    reserved: dict[date, list[tuple[m.Topic, m.Subject, date, int]]] = {}
    for subj in user.subjects:
        exam = subject_exam(subj, today)
        if not exam or exam <= today:
            continue
        for tp in subj.topics:
            have = sum(1 for t in fixed if t.topic_id == tp.id and t.task_type == "revision"
                       and t.status == "pending" and t.date < exam)
            missing = revisions_wanted(tp.mastery) - have
            minutes = 30 if tp.mastery < 40 else 25
            used_days = set()
            for off in (1, 3, 6, 10, 14):
                if missing <= 0:
                    break
                d = exam - timedelta(days=off)
                if d < today or d in used_days or day_capacity(prefs, d) == 0:
                    continue
                reserved.setdefault(d, []).append((tp, subj, exam, minutes))
                used_days.add(d)
                missing -= 1

    # 4) capacity forecast for pacing
    day_list = [today + timedelta(days=i) for i in range((end_day - today).days + 1)] if end_day >= today else []
    room_by_day = {d: max(0, day_capacity(prefs, d) - sum(t.duration_minutes for t in fixed_by_day.get(d, []))) for d in day_list}
    total_need = sum(s.need_left for s in states)
    total_room = sum(room_by_day.values()) - sum(x[3] for v in reserved.values() for x in v)
    if total_need > max(total_room, 0) and states:
        short = total_need - max(total_room, 0)
        summary.warnings.append({"type": "capacity", "minutes": int(short),
                                 "message": f"You need about {round(total_need / 60, 1)}h of study but only have "
                                            f"{round(max(total_room, 0) / 60, 1)}h available before your exams."})

    created: list[m.StudyTask] = []

    def make_task(ts_topic: m.Topic, subj: m.Subject, exam: date | None, day: date, start: int, dur: int,
                  p: ps.Priority, ttype: str, reason: str) -> m.StudyTask:
        t = m.StudyTask(user_id=user.id, subject_id=subj.id, topic_id=ts_topic.id, title=ts_topic.name, task_type=ttype,
                        date=day, start_minute=start, duration_minutes=dur, priority=p.level, priority_score=p.score,
                        difficulty=ts_topic.difficulty, status="pending", origin="generated", reason=reason[:240])
        db.add(t)
        created.append(t)
        return t

    # 5) day loop
    for idx, day in enumerate(day_list):
        cap = day_capacity(prefs, day)
        if cap == 0:
            continue
        fixed_today = fixed_by_day.get(day, [])
        alloc = build_allocator(db, user, day, now, tasks=fixed_today)
        used = sum(t.duration_minutes for t in fixed_today)
        placed = 0
        last_rev_subject = None
        for ts in states:
            ts.placed_today = 0
        prio_cache: dict[int, ps.Priority] = {}

        def prio(tp: m.Topic, subj: m.Subject, exam: date | None) -> ps.Priority:
            if tp.id not in prio_cache:
                boost = (prefs.focus_boosts or {}).get(str(subj.id))
                prio_cache[tp.id] = ps.compute(mastery=tp.mastery, topic_difficulty=tp.difficulty,
                                               subject_importance=subj.importance, target_marks=subj.target_marks,
                                               miss_count=tp.miss_count, last_studied=tp.last_studied, exam_date=exam,
                                               on_date=day, focus_boost=bool(boost and boost >= day.isoformat()))
            return prio_cache[tp.id]

        # reserved pre-exam revisions first
        res_today = sorted(reserved.get(day, []), key=lambda r: -r[0].difficulty)
        interleaved, pools = [], {}
        for r in res_today:
            pools.setdefault(r[1].id, []).append(r)
        while any(pools.values()):                       # alternate subjects so revisions don't clump
            for k in list(pools):
                if pools[k]:
                    interleaved.append(pools[k].pop(0))
        for tp, subj, exam, minutes in interleaved:
            if used + minutes > cap:
                continue
            s = alloc.find(minutes)
            if s is None:
                continue
            p = prio(tp, subj, exam)
            make_task(tp, subj, exam, day, s, minutes, p, "revision",
                      f"Final revision before {subj.name} exam ({(exam - day).days}d left) · {tp.mastery}% mastery")
            alloc.add(s, minutes)
            used += minutes
            placed += minutes
            last_rev_subject = subj.id

        room = cap - used
        if room < 15 or not states:
            continue
        remaining_days = [d for d in day_list[idx:] if room_by_day.get(d, 0) > 0]
        remaining_room = sum(room_by_day[d] for d in remaining_days) or 1
        need_total = sum(s.need_left for s in states if s.exam > day)
        fraction = min(1.0, need_total / remaining_room)
        pace = room * min(1.0, fraction * 1.6)
        must = 0.0
        for subj_id in {s.subject.id for s in states}:
            sub_states = [s for s in states if s.subject.id == subj_id and s.exam > day]
            if not sub_states:
                continue
            exam = sub_states[0].exam
            days_avail = max(1, len([d for d in remaining_days if d < exam]))
            must += 1.3 * sum(s.need_left for s in sub_states) / days_avail
        target = min(room, max(pace, must))
        target = target if target >= 20 else (room if need_total > 0 and room >= 20 and must > 0 else 0)

        last_subject = last_rev_subject
        while target - placed >= 15 and (cap - used) >= 15:
            cands = [s for s in states if s.need_left > 0 and s.exam > day and s.placed_today < 2 * 60]
            if not cands:
                break

            def score(s: TState) -> float:
                p = prio(s.topic, s.subject, s.exam if s.has_exam else None)
                days_avail = max(1, len([d for d in remaining_days if d < s.exam]))
                pressure = s.need_left / days_avail
                adj = p.score * (1 + min(1.5, pressure / 60))
                if s.subject.id == last_subject:
                    adj *= 0.3
                if s.placed_today:
                    adj *= 0.6
                return adj

            ts = max(cands, key=score)
            blen = min(BLOCK_BY_DIFFICULTY[ts.topic.difficulty], prefs.max_block_minutes)
            blen = min(blen, ts.need_left)
            if ts.need_left - blen < 20 and ts.need_left <= prefs.max_block_minutes + 10:
                blen = ts.need_left
            blen = max(15, ceil5(blen))
            blen = min(blen, cap - used, int(target - placed) + 10)
            blen = max(15, ceil5(blen))
            s = alloc.find(blen)
            if s is None and blen > 20:
                blen = 20
                s = alloc.find(blen)
            if s is None:
                break
            p = prio(ts.topic, ts.subject, ts.exam if ts.has_exam else None)
            ttype = "practice" if ts.topic.mastery >= 60 else "study"
            make_task(ts.topic, ts.subject, ts.exam if ts.has_exam else None, day, s, blen, p, ttype,
                      ps.explain(p, ts.topic.mastery, ts.topic.difficulty, ts.topic.miss_count))
            alloc.add(s, blen)
            ts.need_left = max(0, ts.need_left - blen)
            ts.placed_today += blen
            used += blen
            placed += blen
            last_subject = ts.subject.id

    # 6) shortfalls
    short = [s for s in states if s.need_left >= 15]
    for s in sorted(short, key=lambda x: -x.need_left)[:6]:
        summary.warnings.append({"type": "shortfall", "topic": s.topic.name, "subject": s.subject.name,
                                 "minutes": s.need_left,
                                 "message": f"{s.topic.name} ({s.subject.name}) is short by {s.need_left} min before its exam."})

    # 7) restore "moved from" badges on the first new task of each carried topic
    for topic_id, (src, cnt) in carry.items():
        first = min((t for t in created if t.topic_id == topic_id), key=lambda t: (t.date, t.start_minute), default=None)
        if first:
            first.moved_from, first.reschedule_count = src, cnt

    db.flush()
    summary.created = len(created)
    summary.planned_minutes = sum(t.duration_minutes for t in created)
    prefs.last_planned_at = datetime.utcnow()
    return summary


# ---------------------------------------------------------------- overload / balance
def overload_report(db: Session, user: m.User, start: date, end: date) -> list[dict]:
    prefs = user.preferences
    rows = (db.query(m.StudyTask.date, m.StudyTask.duration_minutes).filter(
        m.StudyTask.user_id == user.id, m.StudyTask.date >= start, m.StudyTask.date <= end,
        m.StudyTask.status.in_(ACTIVE)).all())
    by_day: dict[date, int] = {}
    for d, mins in rows:
        by_day[d] = by_day.get(d, 0) + mins
    out = []
    for d, mins in sorted(by_day.items()):
        limit = prefs.max_daily_minutes
        if mins > limit:
            out.append({"date": d, "planned_minutes": mins, "recommended_max": limit})
    return out


def rebalance_day(db: Session, user: m.User, day: date, now: datetime | None = None) -> dict:
    """Move the lowest-priority movable tasks off an overloaded day onto the nearest days with spare room."""
    prefs = user.preferences
    now = now or local_now(prefs.timezone)
    limit = prefs.max_daily_minutes
    tasks = (db.query(m.StudyTask).filter(m.StudyTask.user_id == user.id, m.StudyTask.date == day,
                                          m.StudyTask.status == "pending", m.StudyTask.locked.is_(False)).all())
    total = day_used_minutes(db, user.id, day)
    moved, stuck = [], []
    for t in sorted(tasks, key=lambda t: (ps.LEVEL_RANK[t.priority], t.priority_score)):
        if total <= limit:
            break
        exam = subject_exam(t.subject, now.date())
        latest = (exam - timedelta(days=1)) if exam else day + timedelta(days=14)
        placed = False
        for off in (1, -1, 2, -2, 3, -3, 4, 5, 6, 7):
            d2 = day + timedelta(days=off)
            if d2 < now.date() or d2 > latest or d2 == day:
                continue
            s = find_free_slot(db, user, d2, t.duration_minutes, now=now)
            if s is not None:
                t.moved_from, t.date, t.start_minute = day, d2, s
                t.reschedule_count += 1
                t.reason = f"Rebalanced from {day:%a %d %b} (day was over {limit // 60}h)"[:240]
                total -= t.duration_minutes
                moved.append(t)
                placed = True
                break
        if not placed:
            stuck.append(t)
    db.flush()
    return {"moved": len(moved), "unmovable": len(stuck), "day_minutes_after": total}


# ---------------------------------------------------------------- missed tasks -> auto reschedule
def mark_overdue(db: Session, user: m.User, now: datetime) -> list[m.StudyTask]:
    today, minute = now.date(), now.hour * 60 + now.minute
    rows = db.query(m.StudyTask).filter(m.StudyTask.user_id == user.id,
                                        m.StudyTask.status.in_(("pending", "in_progress")),
                                        m.StudyTask.date <= today).all()
    newly = []
    for t in rows:
        if t.date < today or (t.status == "pending" and t.start_minute + t.duration_minutes + OVERDUE_GRACE < minute):
            t.status = "overdue"
            if t.topic and not t.handled:
                t.topic.miss_count += 1
            newly.append(t)
    db.flush()
    return newly


def link_moved(db: Session, user: m.User, missed: list[m.StudyTask], now: datetime) -> list[dict]:
    """After a replan, tag the next task of each missed topic with where it was moved from."""
    out = []
    for old in missed:
        if not old.topic_id:
            continue
        nxt = (db.query(m.StudyTask).filter(m.StudyTask.user_id == user.id, m.StudyTask.topic_id == old.topic_id,
                                            m.StudyTask.status == "pending", m.StudyTask.date >= now.date(),
                                            m.StudyTask.moved_from.is_(None))
               .order_by(m.StudyTask.date, m.StudyTask.start_minute).first())
        if nxt:
            nxt.moved_from, nxt.reschedule_count = old.date, old.reschedule_count + 1
            nxt.reason = f"Moved from {old.date:%a %d %b} {hhmm(old.start_minute)} (missed) · {nxt.reason}"[:240]
            out.append({"topic": old.title, "from_date": old.date, "from_time": hhmm(old.start_minute),
                        "to_date": nxt.date, "to_time": hhmm(nxt.start_minute), "task_id": nxt.id})
    return out


def sync(db: Session, user: m.User, now: datetime | None = None) -> dict:
    """Detect missed sessions and automatically recompute the remaining plan around them."""
    from . import revision_service  # local import: avoids a cycle
    now = now or local_now(user.preferences.timezone)
    mark_overdue(db, user, now)
    pending_missed = (db.query(m.StudyTask).filter(m.StudyTask.user_id == user.id, m.StudyTask.status == "overdue",
                                                   m.StudyTask.handled.is_(False)).all())
    if not pending_missed:
        return {"missed": 0, "moved": [], "replanned": False}
    spaced = [t for t in pending_missed if t.origin == "spaced"]
    regular = [t for t in pending_missed if t.origin != "spaced"]
    for t in pending_missed:
        t.handled = True
    for t in spaced:
        revision_service.reschedule_review(db, user, t, now)
    moved: list[dict] = []
    replanned = False
    if regular:
        generate(db, user, now)
        moved = link_moved(db, user, regular, now)
        replanned = True
    db.flush()
    return {"missed": len(pending_missed), "moved": moved, "replanned": replanned}
