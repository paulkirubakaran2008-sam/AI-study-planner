"""Rule-based recommendations (always available, always with a stated reason) + optional AI explanations.

The rules read real data: this week's tracked minutes per subject, missed sessions, mastery, planned load, capacity.
AI only *rewords / expands* a recommendation on request (cached, capped); it never decides what is recommended.
"""
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from .. import models as m
from ..timeutil import local_now, monday_of
from . import ai_service
from . import analytics_service as analytics
from . import planner_service as planner
from . import priority_service as ps
from . import streak_service


def _candidates(db: Session, user: m.User, now: datetime) -> list[dict]:
    today, prefs = now.date(), user.preferences
    recs: list[dict] = []
    subjects = {s.id: s for s in user.subjects}
    exams = {s.id: planner.subject_exam(s, today) for s in user.subjects}

    # 1. time imbalance vs. exam proximity
    week_start = monday_of(today)
    tasks, sessions = analytics._range(db, user.id, week_start, today)
    _, per_subject, _ = analytics._actual_by_day(tasks, sessions)
    upcoming = sorted([(exams[sid], sid) for sid in subjects if exams[sid] and (exams[sid] - today).days <= 45])
    if len(upcoming) >= 2:
        (ea, a), (eb, b) = upcoming[0], upcoming[1]
        ma, mb = per_subject.get(a, 0), per_subject.get(b, 0)
        if (eb - ea).days >= 2 and mb - ma >= 30 and today.weekday() >= 1:
            sa, sb = subjects[a], subjects[b]
            weak = min(sa.topics, key=lambda t: t.mastery).name if sa.topics else sa.name
            recs.append({"kind": "time_balance", "severity": "warn", "dedupe_key": f"balance:{a}:{b}:{week_start}",
                         "title": f"Shift 30 minutes from {sb.name} to {sa.name}",
                         "body": f"You've spent less time on {sa.name} than {sb.name} this week, but your {sa.name} exam is closer.",
                         "reason": f"{sa.name} exam in {(ea - today).days} days vs {(eb - today).days} for {sb.name}; you tracked "
                                   f"{ma} min on {sa.name} and {mb} min on {sb.name} since Monday. Start with {weak}.",
                         "action": {"type": "shift_minutes", "from_subject_id": b, "to_subject_id": a, "minutes": 30}})

    # 2. missed sessions yesterday -> lighter day
    y = today - timedelta(days=1)
    missed_y = [t for t in db.query(m.StudyTask).filter(m.StudyTask.user_id == user.id, m.StudyTask.date == y,
                                                       m.StudyTask.status.in_(("skipped", "overdue"))).all()]
    if len(missed_y) >= 2 and planner.day_used_minutes(db, user.id, today) > 90:
        recs.append({"kind": "reduce_load", "severity": "warn", "dedupe_key": f"easeday:{today}",
                     "title": "Lighten today instead of piling on",
                     "body": f"You missed {len(missed_y)} study sessions yesterday. A packed day now is likely to fail again.",
                     "reason": "Two or more misses in a day usually mean the plan was too heavy for that day. Cutting today's load to ~70% "
                               "and spreading the rest over later days keeps the schedule believable.",
                     "action": {"type": "ease_day", "date": today.isoformat(), "factor": 0.7}})

    # 3. weak topics with too few revisions
    for s in user.subjects:
        exam = exams[s.id]
        if not exam or (exam - today).days > 30:
            continue
        for tp in s.topics:
            if tp.mastery < 40:
                have = db.query(m.StudyTask).filter(m.StudyTask.topic_id == tp.id, m.StudyTask.task_type == "revision",
                                                    m.StudyTask.status == "pending", m.StudyTask.date >= today,
                                                    m.StudyTask.date < exam).count()
                if have < 3:
                    recs.append({"kind": "weak_topic", "severity": "warn", "dedupe_key": f"weak:{tp.id}:{tp.mastery // 10}",
                                 "title": f"Revise {tp.name} more before {s.name}",
                                 "body": f"Your {tp.name} topic has only {tp.mastery}% mastery. Schedule {3 - have} more revision session(s) before your exam.",
                                 "reason": f"Topics under 40% mastery need ~3 spaced reviews to stick. {tp.name} has {have} scheduled and the "
                                           f"{s.name} exam is in {(exam - today).days} days.",
                                 "action": {"type": "add_revisions", "topic_id": tp.id, "count": 3 - have}})

    # 4. overload
    for row in planner.overload_report(db, user, today, today + timedelta(days=14))[:2]:
        d = row["date"]
        recs.append({"kind": "overload", "severity": "urgent", "dedupe_key": f"overload:{d}:{row['planned_minutes']}",
                     "title": f"{d:%A}'s plan is {row['planned_minutes'] / 60:.1f}h — too much",
                     "body": f"Your {d:%A} plan contains {row['planned_minutes'] / 60:.1f} hours. Recommended maximum: {row['recommended_max'] / 60:.1f} hours.",
                     "reason": "Long days hurt retention and make missed sessions more likely. I can move the lowest-priority sessions to nearby days.",
                     "action": {"type": "rebalance", "date": d.isoformat()}})

    # 5. capacity shortfall
    horizon = [today + timedelta(days=i) for i in range(0, 60)]
    need = 0
    cap = 0
    last_exam = max([e for e in exams.values() if e] + [today])
    for s in user.subjects:
        e = exams[s.id]
        if e and e > today:
            need += sum(ps.minutes_needed(t.mastery, t.difficulty, s.target_marks) for t in s.topics)
    cap = sum(planner.day_capacity(prefs, d) for d in horizon if d < last_exam)
    if need > cap > 0 or (need > 0 and cap == 0):
        extra = max(15, (need - cap) // max(1, (last_exam - today).days) // 15 * 15 + 15)
        base = max(prefs.daily_minutes)
        recs.append({"kind": "capacity", "severity": "urgent", "dedupe_key": f"capacity:{need // 60}:{cap // 60}",
                     "title": "Your goals need more time than you have",
                     "body": f"Your topics need about {need / 60:.1f}h of study but only {cap / 60:.1f}h is available before your last exam.",
                     "reason": f"Either add about {extra} min per day, lower a target mark, or accept lower mastery on easy topics.",
                     "action": {"type": "set_daily_minutes", "minutes": min(600, base + extra)}})

    # 6. exam imminent
    for s in user.subjects:
        e = exams[s.id]
        if e and 0 < (e - today).days <= 3:
            weak = sorted(s.topics, key=lambda t: t.mastery)[:2]
            recs.append({"kind": "exam_soon", "severity": "urgent", "dedupe_key": f"examsoon:{s.id}:{e}",
                         "title": f"{s.name} exam in {(e - today).days} day(s)",
                         "body": "Switch to revision and past questions. Focus on: " + ", ".join(f"{t.name} ({t.mastery}%)" for t in weak) + ".",
                         "reason": "In the final days, revisiting weak topics beats learning new material.",
                         "action": {"type": "focus_subject", "subject": s.name, "days": max(1, (e - today).days)}})

    # 7. streak at risk
    st = streak_service.summary(db, user.id, today)
    if st["current"] >= 2 and not st["studied_today"] and now.hour >= 17:
        recs.append({"kind": "streak", "severity": "info", "dedupe_key": f"streak:{today}",
                     "title": f"Keep your {st['current']}-day streak alive",
                     "body": "Ten focused minutes today is enough to keep the streak going.",
                     "reason": "A study day counts once you've logged 10 minutes with the Focus timer or completed a task.", "action": None})
    return recs


def refresh(db: Session, user: m.User, now: datetime | None = None) -> list[m.AIRecommendation]:
    now = now or local_now(user.preferences.timezone)
    cands = _candidates(db, user, now)
    existing = {r.dedupe_key: r for r in db.query(m.AIRecommendation).filter(m.AIRecommendation.user_id == user.id,
                                                                            m.AIRecommendation.created_at > datetime.utcnow() - timedelta(days=21)).all()}
    keys = set()
    for c in cands:
        keys.add(c["dedupe_key"])
        if c["dedupe_key"] not in existing:
            db.add(m.AIRecommendation(user_id=user.id, source="rules", **c))
    for key, r in existing.items():
        if r.status == "active" and key not in keys:
            r.status = "stale"
    db.flush()
    return (db.query(m.AIRecommendation).filter(m.AIRecommendation.user_id == user.id, m.AIRecommendation.status == "active")
            .order_by(m.AIRecommendation.id.desc()).all())


SEVERITY_RANK = {"urgent": 0, "warn": 1, "info": 2}


def sorted_active(recs: list[m.AIRecommendation]) -> list[m.AIRecommendation]:
    return sorted(recs, key=lambda r: (SEVERITY_RANK.get(r.severity, 3), -r.id))


# ---- AI (optional, cached, capped) -------------------------------------------------------
EXPLAIN_SYSTEM = ("You are a calm, practical study coach. In 2-3 short sentences explain why this recommendation helps a college "
                  "student, using only the facts given. No lists, no emojis, no new numbers.")


def explain(db: Session, user: m.User, rec: m.AIRecommendation) -> str:
    prompt = f"Recommendation: {rec.title}. Situation: {rec.body} Reasoning: {rec.reason}"
    text, _ = ai_service.complete(db, user, system=EXPLAIN_SYSTEM, prompt=prompt, max_tokens=160)
    rec.ai_explanation = text.strip()
    return rec.ai_explanation


STRATEGY_SYSTEM = ("You are a study strategist. Given a compact weekly summary, give exactly 3 concrete tips for the next 7 days, "
                   "one per line, each under 28 words, each tied to a number in the summary. No preamble.")


def strategy(db: Session, user: m.User, now: datetime | None = None) -> tuple[str, bool]:
    now = now or local_now(user.preferences.timezone)
    today = now.date()
    rep = analytics.report(db, user, today, 7)
    exams = [(s.name, (planner.subject_exam(s, today) - today).days, min((t.mastery for t in s.topics), default=0))
             for s in user.subjects if planner.subject_exam(s, today)]
    summary = (f"completion {rep['completion_rate']}%; studied {rep['productivity']['actual_minutes']} of "
               f"{rep['productivity']['planned_minutes']} planned min; missed {rep['productivity']['missed_tasks']}; "
               f"streak {rep['streak']['current']}; score {rep['score']['score']}; "
               "exams: " + ", ".join(f"{n} in {d}d (weakest topic {w}%)" for n, d, w in sorted(exams, key=lambda x: x[1])[:5]))
    return ai_service.complete(db, user, system=STRATEGY_SYSTEM, prompt=summary, max_tokens=220)
