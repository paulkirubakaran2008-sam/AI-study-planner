from datetime import date, datetime, timedelta

from app import models as m
from app.services import (analytics_service, assistant_service, planner_service as planner, priority_service as ps,
                          revision_service, streak_service)
from app.timeutil import local_now

from .conftest import onboarding_payload


# ---------------------------------------------------------------- auth
def test_register_login_and_password_hashing(client, db):
    r = client.post("/api/auth/register", json={"name": "A", "email": "a@x.com", "password": "password123"})
    assert r.status_code == 201
    assert client.post("/api/auth/register", json={"name": "A", "email": "A@x.com", "password": "password123"}).status_code == 409
    row = db.query(m.User).filter_by(email="a@x.com").one()
    assert "password123" not in row.password_hash and row.password_hash.startswith("$2")
    ok = client.post("/api/auth/login", json={"email": "a@x.com", "password": "password123"})
    assert ok.status_code == 200 and ok.json()["access_token"]
    assert client.post("/api/auth/login", json={"email": "a@x.com", "password": "wrong-password"}).status_code == 401
    assert client.post("/api/auth/register", json={"name": "B", "email": "b@x.com", "password": "short"}).status_code == 422


def test_protected_routes_need_token_and_users_are_isolated(client, planned):
    assert client.get("/api/tasks").status_code == 401
    headers, _, _ = planned
    tasks = client.get("/api/tasks", headers=headers).json()
    assert tasks
    other = client.post("/api/auth/register", json={"name": "O", "email": "other@x.com", "password": "password123"}).json()
    oh = {"Authorization": f"Bearer {other['access_token']}"}
    assert client.get("/api/tasks", headers=oh).json() == []
    assert client.post(f"/api/tasks/{tasks[0]['id']}/complete", json={}, headers=oh).status_code == 404
    assert client.delete(f"/api/tasks/{tasks[0]['id']}", headers=oh).status_code == 404


def test_request_size_limit(client, auth):
    headers, _ = auth
    r = client.post("/api/assistant/interpret", content=b"x" * 300_000, headers={**headers, "Content-Type": "application/json"})
    assert r.status_code == 413


# ---------------------------------------------------------------- priority
def test_priority_ordering_and_normalisation():
    base = dict(topic_difficulty=3, subject_importance=3, target_marks=80, miss_count=0, last_studied=date.today(), on_date=date.today())
    weak_soon = ps.compute(mastery=20, exam_date=date.today() + timedelta(days=3), **base)
    strong_far = ps.compute(mastery=90, exam_date=date.today() + timedelta(days=40), **base)
    assert 0 <= strong_far.score < weak_soon.score <= 1
    assert weak_soon.level in ("critical", "high") and strong_far.level == "low"
    missed = ps.compute(mastery=50, exam_date=date.today() + timedelta(days=10), **{**base, "miss_count": 3})
    fresh = ps.compute(mastery=50, exam_date=date.today() + timedelta(days=10), **base)
    assert missed.score > fresh.score
    assert abs(sum(ps.WEIGHTS.values()) - 1) < 1e-9


# ---------------------------------------------------------------- plan generation invariants
def test_plan_respects_all_constraints(client, planned, db):
    headers, uid, summary = planned
    assert summary["created"] > 0
    user = db.get(m.User, uid)
    prefs = user.preferences
    tasks = db.query(m.StudyTask).filter_by(user_id=uid).order_by(m.StudyTask.date, m.StudyTask.start_minute).all()
    exams = {s.id: max(e.exam_date for e in s.exams) for s in user.subjects}
    by_day: dict = {}
    for t in tasks:
        assert t.date < exams[t.subject_id], "task scheduled on/after its exam"
        assert t.start_minute >= prefs.wake_time and t.start_minute + t.duration_minutes <= prefs.sleep_start
        assert t.duration_minutes <= 60
        by_day.setdefault(t.date, []).append(t)
    for d, ts in by_day.items():
        assert sum(x.duration_minutes for x in ts) <= planner.day_capacity(prefs, d), f"over capacity on {d}"
        ts.sort(key=lambda x: x.start_minute)
        for a, b in zip(ts, ts[1:]):
            assert b.start_minute - (a.start_minute + a.duration_minutes) >= prefs.break_minutes, "missing break"
    # weak + urgent topics get more time than strong ones
    minutes = {}
    for t in tasks:
        minutes[t.title] = minutes.get(t.title, 0) + t.duration_minutes
    assert minutes["Graphs"] > minutes["Arrays"] and minutes["Trees"] > minutes["Arrays"]
    assert any(t.task_type == "revision" for t in tasks), "pre-exam revisions missing"


def test_plan_uses_subject_variation(client, db):
    from itertools import groupby
    body = client.post("/api/demo/start", json={}).json()
    tasks = db.query(m.StudyTask).filter(m.StudyTask.user_id == body["user"]["id"], m.StudyTask.date >= date.today(), m.StudyTask.task_type != "revision").order_by(m.StudyTask.date, m.StudyTask.start_minute).all()
    same = total = 0   # final-revision days intentionally focus one exam, so variation is measured on study/practice blocks
    for _, grp in groupby(tasks, key=lambda t: t.date):
        g = list(grp)
        for a, b in zip(g, g[1:]):
            total += 1
            same += a.subject_id == b.subject_id
    assert total and same / total < 0.5


def test_overload_is_detected_and_rebalanced(client, planned, db):
    headers, uid, _ = planned
    user = db.get(m.User, uid)
    day = local_now(user.preferences.timezone).date() + timedelta(days=2)
    subj = user.subjects[0]
    for i in range(7):
        db.add(m.StudyTask(user_id=uid, subject_id=subj.id, topic_id=subj.topics[1].id, title="extra", date=day, start_minute=6 * 60 + i * 130,
                           duration_minutes=60, priority="low", origin="generated"))
    db.commit()
    report = planner.overload_report(db, user, day, day)
    assert report and report[0]["planned_minutes"] > user.preferences.max_daily_minutes
    res = client.post("/api/planner/rebalance", json={"date": str(day)}, headers=headers).json()
    assert res["moved"] > 0
    db.expire_all()
    assert planner.day_used_minutes(db, uid, day) < report[0]["planned_minutes"]


# ---------------------------------------------------------------- completion, revision, mastery
def _first_pending(client, headers):
    return next(t for t in client.get("/api/tasks", headers=headers).json() if t["status"] == "pending" and t["task_type"] != "revision")


def test_complete_raises_mastery_and_schedules_spaced_review(client, planned, db):
    headers, uid, _ = planned
    t = _first_pending(client, headers)
    before = db.get(m.Topic, t["topic_id"]).mastery
    r = client.post(f"/api/tasks/{t['id']}/complete", json={"confidence": 4, "actual_minutes": t["duration_minutes"]}, headers=headers)
    assert r.status_code == 200 and r.json()["task"]["status"] == "completed"
    db.expire_all()
    assert db.get(m.Topic, t["topic_id"]).mastery > before
    reviews = db.query(m.StudyTask).filter_by(user_id=uid, origin="spaced", topic_id=t["topic_id"]).all()
    assert len(reviews) == 1 and reviews[0].task_type == "revision" and reviews[0].date > local_now("Asia/Kolkata").date() - timedelta(days=1)
    assert client.post(f"/api/tasks/{t['id']}/complete", json={}, headers=headers).status_code == 409


def test_spaced_repetition_intervals():
    assert revision_service.next_stage_and_interval(0, 2, False) == (0, 1)       # low confidence -> tomorrow
    assert revision_service.next_stage_and_interval(0, 5, False)[1] == 3          # high -> longer
    assert revision_service.next_stage_and_interval(1, 3, True) == (2, 7)         # 1d -> 3d -> 7d
    assert revision_service.next_stage_and_interval(2, 5, True) == (4, 30)        # very high skips a rung
    stage, interval = revision_service.next_stage_and_interval(3, 1, True)        # low confidence goes back & shortens
    assert stage == 2 and interval == 3
    assert [revision_service.LADDER[i] for i in range(4)] == [1, 3, 7, 14]


def test_review_never_scheduled_on_or_after_exam(client, auth, db):
    headers, uid = auth
    payload = onboarding_payload((3, 20))
    client.post("/api/onboarding", json=payload, headers=headers)
    t = next(x for x in client.get("/api/tasks", headers=headers).json() if x["subject_name"] == "Data Structures" and x["task_type"] != "revision")
    client.post(f"/api/tasks/{t['id']}/complete", json={"confidence": 5}, headers=headers)
    exam = db.query(m.Exam).join(m.Subject).filter(m.Subject.user_id == uid, m.Subject.name == "Data Structures").one().exam_date
    for r in db.query(m.StudyTask).filter_by(user_id=uid, origin="spaced"):
        assert r.date < exam


# ---------------------------------------------------------------- skip + auto reschedule
def test_skip_reschedules_instead_of_just_shifting(client, planned, db):
    headers, uid, _ = planned
    t = _first_pending(client, headers)
    r = client.post(f"/api/tasks/{t['id']}/skip", json={"reschedule": True}, headers=headers).json()
    assert r["task"]["status"] == "skipped" and r["replanned"]
    db.expire_all()
    assert db.get(m.Topic, t["topic_id"]).miss_count >= 1
    nxt = [x for x in client.get("/api/tasks", headers=headers).json() if x["topic_id"] == t["topic_id"] and x["status"] == "pending"]
    assert nxt, "topic must still be scheduled after a skip"
    assert any(x["moved_from"] == t["date"] for x in nxt) or r["moved"]


def test_missed_sessions_are_detected_and_plan_is_rebuilt(client, planned, db):
    headers, uid, _ = planned
    user = db.get(m.User, uid)
    now = local_now(user.preferences.timezone)
    first = db.query(m.StudyTask).filter_by(user_id=uid).order_by(m.StudyTask.date, m.StudyTask.start_minute).first()
    topic_id = first.topic_id
    future_now = datetime.combine(first.date, datetime.min.time()) + timedelta(minutes=first.start_minute + first.duration_minutes + 120)
    res = planner.sync(db, user, future_now)
    db.commit()
    assert res["missed"] >= 1 and res["replanned"]
    db.expire_all()
    assert db.get(m.StudyTask, first.id).status == "overdue" and db.get(m.StudyTask, first.id).handled
    later = db.query(m.StudyTask).filter(m.StudyTask.user_id == uid, m.StudyTask.topic_id == topic_id, m.StudyTask.status == "pending",
                                         m.StudyTask.date >= future_now.date()).all()
    assert later, "missed topic is scheduled again"
    assert planner.sync(db, db.get(m.User, uid), future_now)["missed"] == 0   # idempotent
    # nothing planned in the past
    assert not db.query(m.StudyTask).filter(m.StudyTask.user_id == uid, m.StudyTask.status == "pending", m.StudyTask.date < future_now.date()).count()


# ---------------------------------------------------------------- tasks CRUD / calendar
def test_task_crud_move_overlap_and_validation(client, planned):
    headers, _, _ = planned
    tasks = client.get("/api/tasks", headers=headers).json()
    t = next(x for x in tasks if x["status"] == "pending")
    target = (date.today() + timedelta(days=5)).isoformat()
    r = client.put(f"/api/tasks/{t['id']}", json={"date": target, "start_time": "14:00", "duration_minutes": 30}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["date"] == target and body["duration_minutes"] == 30 and body["locked"]
    assert client.put(f"/api/tasks/{t['id']}", json={"date": "2020-01-01"}, headers=headers).status_code == 422
    assert client.put(f"/api/tasks/{t['id']}", json={"status": "completed"}, headers=headers).status_code == 422
    created = client.post("/api/tasks", json={"subject_id": t["subject_id"], "topic_id": t["topic_id"], "date": target, "start_time": "14:10", "duration_minutes": 30}, headers=headers)
    assert created.status_code == 201
    assert created.json()["start_time"] != "14:10", "overlapping manual task must be nudged to a free slot"
    assert client.delete(f"/api/tasks/{created.json()['id']}", headers=headers).status_code == 204
    assert client.post("/api/tasks", json={"subject_id": t["subject_id"], "date": target, "start_time": "25:00"}, headers=headers).status_code == 422


def test_manual_tasks_survive_replanning(client, planned):
    headers, _, _ = planned
    t = next(x for x in client.get("/api/tasks", headers=headers).json() if x["status"] == "pending")
    day = (date.today() + timedelta(days=3)).isoformat()
    created = client.post("/api/tasks", json={"subject_id": t["subject_id"], "date": day, "start_time": "10:30", "duration_minutes": 40, "title": "My own session"}, headers=headers).json()
    client.post("/api/planner/generate", headers=headers)
    assert any(x["id"] == created["id"] for x in client.get("/api/tasks", headers=headers).json())


# ---------------------------------------------------------------- assistant
def test_assistant_parses_and_applies_structured_actions(client, planned):
    headers, _, _ = planned
    r = client.post("/api/assistant/interpret", json={"text": "Study Trees tomorrow for 1 hour"}, headers=headers).json()
    assert r["understood"] and r["actions"][0]["type"] == "add_task" and r["actions"][0]["duration_minutes"] == 60 and r["source"] == "rules"
    applied = client.post("/api/assistant/apply", json={"actions": r["actions"]}, headers=headers).json()
    assert applied["results"][0]["ok"], applied
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert any(t["topic_name"] == "Trees" and t["date"] == tomorrow and t["duration_minutes"] == 60 for t in client.get("/api/tasks", headers=headers).json())

    r2 = client.post("/api/assistant/interpret", json={"text": "Give me 30 minutes of revision tonight"}, headers=headers).json()
    assert r2["actions"][0]["type"] == "add_revision" and r2["actions"][0]["duration_minutes"] == 30

    r3 = client.post("/api/assistant/interpret", json={"text": "Move Virtual Memory to Saturday"}, headers=headers).json()
    assert r3["actions"][0]["type"] == "move_task" and r3["actions"][0]["to_date"]
    res = client.post("/api/assistant/apply", json={"actions": r3["actions"]}, headers=headers).json()["results"][0]
    assert res["ok"], res


def test_assistant_blocks_a_day_and_replans(client, planned):
    headers, _, _ = planned
    r = client.post("/api/assistant/interpret", json={"text": "I cannot study tomorrow. Adjust my schedule."}, headers=headers).json()
    assert r["actions"][0]["type"] == "block_day"
    client.post("/api/assistant/apply", json={"actions": r["actions"]}, headers=headers)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    day_tasks = [t for t in client.get("/api/tasks", headers=headers).json() if t["date"] == tomorrow and t["status"] == "pending"]
    assert day_tasks == []


def test_assistant_easier_plan_and_rejects_unsafe_input(client, planned):
    headers, _, _ = planned
    r = client.post("/api/assistant/interpret", json={"text": "I have an exam in 10 days and only 2 hours per day. Make my plan easier."}, headers=headers).json()
    assert r["actions"][0]["type"] == "set_daily_limit" and r["actions"][0]["minutes"] == 120
    client.post("/api/assistant/apply", json={"actions": r["actions"]}, headers=headers)
    per_day: dict = {}
    for t in client.get("/api/tasks", headers=headers).json():
        if t["status"] == "pending" and t["date"] > date.today().isoformat() and t["date"] <= (date.today() + timedelta(days=9)).isoformat():
            per_day[t["date"]] = per_day.get(t["date"], 0) + t["duration_minutes"]
    assert per_day and max(per_day.values()) <= 120
    # arbitrary / malicious actions are rejected by the whitelist, never executed
    bad = client.post("/api/assistant/apply", json={"actions": [{"type": "drop_table", "name": "users"}]}, headers=headers)
    assert bad.status_code == 422
    unknown = client.post("/api/assistant/interpret", json={"text": "tell me a joke"}, headers=headers).json()
    assert unknown["understood"] is False and unknown["actions"] == []


def test_assistant_ai_actions_are_validated(db, planned, monkeypatch):
    _, uid, _ = planned
    user = db.get(m.User, uid)
    from app.services import ai_service
    monkeypatch.setattr(ai_service, "is_enabled", lambda: True)
    monkeypatch.setattr(ai_service, "complete", lambda *a, **k: ('{"reply":"ok","actions":[{"type":"add_task","subject":"Nonexistent","date":"2099-01-01"},'
                                                                  '{"type":"delete_everything"},{"type":"focus_subject","subject":"Data Structures","days":5}]}', False))
    out = assistant_service.interpret(db, user, "please make my week about the thing")
    assert out["source"] == "ai"
    assert [a["type"] for a in out["actions"]] == ["focus_subject"]
    assert out["errors"]


# ---------------------------------------------------------------- AI degraded mode
def test_planner_and_recommendations_work_without_ai(client, planned):
    headers, _, _ = planned
    assert client.get("/api/dashboard", headers=headers).status_code == 200
    recs = client.get("/api/recommendations", headers=headers).json()
    assert recs["ai"]["enabled"] is False
    client.put("/api/settings", json={"daily_minutes": [30] * 7, "max_daily_minutes": 60}, headers=headers)   # force a capacity shortfall
    recs = client.get("/api/recommendations", headers=headers).json()
    assert recs["items"], "rule engine should flag the shortfall without any AI"
    assert all(r["reason"] for r in recs["items"]), "every recommendation must explain why"
    rid = recs["items"][0]["id"]
    ex = client.post(f"/api/recommendations/{rid}/explain", headers=headers).json()
    assert ex["available"] is False and "temporarily unavailable" in ex["message"]
    st = client.post("/api/recommendations/strategy", headers=headers).json()
    assert st["available"] is False
    assert client.post("/api/planner/generate", headers=headers).status_code == 200


def test_ai_failure_is_graceful(db, planned, monkeypatch):
    _, uid, _ = planned
    user = db.get(m.User, uid)
    from app.services import ai_service
    monkeypatch.setenv("AI_API_KEY", "x")
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setattr(ai_service, "_call_provider", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    try:
        import pytest
        with pytest.raises(ai_service.AIUnavailable):
            ai_service.complete(db, user, system="s", prompt="p")
    finally:
        monkeypatch.delenv("AI_API_KEY")
        get_settings.cache_clear()
        ai_service._failures.update(count=0, open_until=0.0)


def test_ai_results_are_cached_and_capped(db, planned, monkeypatch):
    _, uid, _ = planned
    user = db.get(m.User, uid)
    from app.services import ai_service
    from app.config import get_settings
    monkeypatch.setenv("AI_API_KEY", "x")
    monkeypatch.setenv("AI_DAILY_LIMIT_PER_USER", "2")
    get_settings.cache_clear()
    calls = []
    monkeypatch.setattr(ai_service, "_call_provider", lambda s, p, n: calls.append(p) or f"answer:{p}")
    try:
        assert ai_service.complete(db, user, system="s", prompt="same") == ("answer:same", False)
        assert ai_service.complete(db, user, system="s", prompt="same") == ("answer:same", True)
        assert len(calls) == 1
        ai_service.complete(db, user, system="s", prompt="other")
        import pytest
        with pytest.raises(ai_service.AIUnavailable):
            ai_service.complete(db, user, system="s", prompt="third")
    finally:
        monkeypatch.delenv("AI_API_KEY")
        monkeypatch.delenv("AI_DAILY_LIMIT_PER_USER")
        get_settings.cache_clear()


# ---------------------------------------------------------------- streak / analytics / score
def test_streak_calculation():
    today = date(2026, 10, 8)
    days = {today - timedelta(days=i) for i in (1, 2, 3, 4)} | {today - timedelta(days=i) for i in (8, 9, 10, 11, 12, 13)}
    assert streak_service.compute(days, today) == (4, 6)           # streak still alive if today hasn't been studied yet
    assert streak_service.compute(days | {today}, today) == (5, 6)
    assert streak_service.compute({today - timedelta(days=3)}, today) == (0, 1)
    assert streak_service.compute(set(), today) == (0, 0)


def test_analytics_and_score_use_real_data(client, planned, db):
    headers, uid, _ = planned
    base = client.get("/api/analytics", headers=headers).json()
    assert base["score"]["score"] >= 0 and base["productivity"]["actual_minutes"] == 0 and base["streak"]["current"] == 0
    t = _first_pending(client, headers)
    client.post("/api/sessions", json={"task_id": t["id"], "duration_minutes": 40, "planned_minutes": 45, "mode": "focus", "confidence": 4, "complete_task": True}, headers=headers)
    after = client.get("/api/analytics", headers=headers).json()
    assert after["productivity"]["actual_minutes"] == 40 and after["productivity"]["focus_sessions"] == 1
    assert after["streak"]["current"] == 1 and after["streak"]["studied_today"] and after["streak"]["total_hours"] == 0.7
    assert after["score"]["focus"] > 0 and after["score"]["completion"] == 100
    s = after["score"]
    assert s["score"] == round(0.3 * s["consistency"] + 0.3 * s["completion"] + 0.2 * s["focus"] + 0.2 * s["planning"]) or abs(s["score"] - (0.3 * s["consistency"] + 0.3 * s["completion"] + 0.2 * s["focus"] + 0.2 * s["planning"])) <= 1
    assert after["subject_distribution"][0]["minutes"] == 40


def test_focus_session_without_task_updates_topic(client, planned, db):
    headers, uid, _ = planned
    topic = db.query(m.Topic).join(m.Subject).filter(m.Subject.user_id == uid, m.Topic.name == "Trees").one()
    r = client.post("/api/sessions", json={"subject_id": topic.subject_id, "topic_id": topic.id, "duration_minutes": 25, "mode": "pomodoro", "confidence": 5}, headers=headers)
    assert r.status_code == 201
    db.expire_all()
    assert db.get(m.Topic, topic.id).mastery > 30
    assert client.post("/api/sessions", json={"duration_minutes": 0}, headers=headers).status_code == 422


# ---------------------------------------------------------------- subjects, settings, dashboard, notifications, demo
def test_subject_topic_exam_management_replans(client, planned):
    headers, _, _ = planned
    before = len(client.get("/api/tasks", headers=headers).json())
    new = client.post("/api/subjects", json={"name": "Python", "difficulty": 2, "exam_date": str(date.today() + timedelta(days=12)),
                                              "topics": [{"name": "Functions", "difficulty": 2, "mastery": 20}]}, headers=headers)
    assert new.status_code == 201 and new.json()["days_left"] == 12
    assert client.post("/api/subjects", json={"name": "python"}, headers=headers).status_code == 409
    after = client.get("/api/tasks", headers=headers).json()
    assert any(t["subject_name"] == "Python" for t in after)
    sid = new.json()["id"]
    t = client.post(f"/api/subjects/{sid}/topics", json={"name": "Classes", "difficulty": 3, "mastery": 10}, headers=headers).json()
    assert client.put(f"/api/topics/{t['id']}", json={"mastery": 70}, headers=headers).json()["mastery"] == 70
    assert client.put(f"/api/subjects/{sid}", json={"exam_date": str(date.today() + timedelta(days=20))}, headers=headers).json()["days_left"] == 20
    assert client.delete(f"/api/topics/{t['id']}", headers=headers).status_code == 204
    assert client.delete(f"/api/subjects/{sid}", headers=headers).status_code == 204
    assert not any(t["subject_name"] == "Python" for t in client.get("/api/tasks", headers=headers).json())
    assert client.put(f"/api/topics/{t['id']}", json={"mastery": 101}, headers=headers).status_code in (404, 422)


def test_settings_update_changes_plan_capacity(client, planned):
    headers, _, _ = planned
    r = client.put("/api/settings", json={"daily_minutes": [60] * 7, "max_daily_minutes": 90, "theme": "dark"}, headers=headers)
    assert r.status_code == 200 and r.json()["theme"] == "dark"
    per_day: dict = {}
    for t in client.get("/api/tasks", headers=headers).json():
        if t["status"] == "pending":
            per_day[t["date"]] = per_day.get(t["date"], 0) + t["duration_minutes"]
    assert max(per_day.values()) <= 60
    assert client.put("/api/settings", json={"daily_minutes": [60] * 3}, headers=headers).status_code == 422
    assert client.put("/api/settings", json={"timezone": "Mars/Base"}, headers=headers).status_code == 422


def test_dashboard_contents(client, planned):
    headers, _, _ = planned
    d = client.get("/api/dashboard", headers=headers).json()
    assert d["name"] == "Sam" and d["next_exam"]["subject"] == "Data Structures" and 9 <= d["next_exam"]["days_left"] <= 10
    assert 0 <= d["next_exam"]["preparation"] <= 100 and d["next_exam"]["seconds_remaining"] > 0
    assert d["next_exam"]["recommended"].startswith("Study")
    assert "streak" in d and "score" in d and "stats" in d


def test_notifications_are_generated_once(client, planned):
    headers, _, _ = planned
    client.get("/api/dashboard", headers=headers)
    first = client.get("/api/notifications", headers=headers).json()
    second = client.get("/api/notifications", headers=headers).json()
    assert len(first["items"]) == len(second["items"])
    if first["items"]:
        nid = first["items"][0]["id"]
        client.post(f"/api/notifications/{nid}/read", headers=headers)
        client.post("/api/notifications/read-all", headers=headers)
        assert client.get("/api/notifications", headers=headers).json()["unread"] == 0


def test_demo_mode_is_isolated(client, db):
    r = client.post("/api/demo/start", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["is_demo"] and body["user"]["name"] == "Sam"
    h = {"Authorization": f"Bearer {body['access_token']}"}
    subs = client.get("/api/subjects", headers=h).json()
    assert {s["name"] for s in subs} >= {"Data Structures", "Operating Systems", "Python", "Java"}
    ds = next(s for s in subs if s["name"] == "Data Structures")
    assert ds["days_left"] == 12 and {t["name"]: t["mastery"] for t in ds["topics"]}["Trees"] == 30
    dash = client.get("/api/dashboard", headers=h).json()
    assert dash["streak"]["current"] == 7 and dash["streak"]["total_hours"] > 0
    assert client.post("/api/auth/login", json={"email": body["user"]["email"], "password": "x"}).status_code == 401
    second = client.post("/api/demo/start", json={}).json()
    h2 = {"Authorization": f"Bearer {second['access_token']}"}
    assert second["user"]["id"] != body["user"]["id"]
    t = client.get("/api/tasks", headers=h).json()[0]
    assert client.delete(f"/api/tasks/{t['id']}", headers=h2).status_code == 404
    real = client.post("/api/auth/register", json={"name": "R", "email": "real@x.com", "password": "password123"}).json()
    assert client.get("/api/subjects", headers={"Authorization": f"Bearer {real['access_token']}"}).json() == []


def test_onboarding_validation(client, auth):
    headers, _ = auth
    bad = onboarding_payload()
    bad["subjects"][1]["name"] = "data structures"
    assert client.post("/api/onboarding", json=bad, headers=headers).status_code == 422
    bad2 = onboarding_payload()
    bad2["weekday_minutes"] = 9999
    assert client.post("/api/onboarding", json=bad2, headers=headers).status_code == 422
    ok = client.post("/api/onboarding", json=onboarding_payload(), headers=headers)
    assert ok.status_code == 201
    assert client.post("/api/onboarding", json=onboarding_payload(), headers=headers).status_code == 409


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_notification_generation_is_race_safe(client, planned, db):
    from app.services import notification_service
    user = db.get(m.User, planned[1])
    notification_service.generate(db, user)
    db.commit()
    # simulate a concurrent request that did not see the first one's rows: same key inserted again must be a no-op
    notification_service._add(db, user, set(), "daily_plan", f"daily:{date.today()}", "dup", "")
    notification_service._add(db, user, set(), "daily_plan", f"daily:{date.today()}", "dup", "")
    db.commit()
    keys = [k for (k,) in db.query(m.Notification.dedupe_key).filter_by(user_id=planned[1])]
    assert len(keys) == len(set(keys))
