import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["ENVIRONMENT"] = "development"
os.environ["AI_API_KEY"] = ""
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-only-0123456789"

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.security import auth_limiter, demo_limiter


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_limits():
    auth_limiter.hits.clear()
    demo_limiter.hits.clear()


_counter = {"n": 0}


@pytest.fixture
def auth(client):
    """Registers a fresh user, returns (headers, user_id)."""
    _counter["n"] += 1
    r = client.post("/api/auth/register", json={"name": "Sam", "email": f"sam{_counter['n']}@example.com", "password": "correct-horse-1", "timezone": "Asia/Kolkata"})
    assert r.status_code == 201, r.text
    body = r.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def onboarding_payload(days_to_exam=(10, 18)):
    from datetime import date, timedelta
    today = date.today()
    return {
        "profile": {"name": "Sam", "college": "RTC", "department": "CSE", "year": 2},
        "subjects": [
            {"name": "Data Structures", "difficulty": 4, "importance": 5, "target_marks": 85, "exam_date": str(today + timedelta(days=days_to_exam[0])),
             "topics": [{"name": "Arrays", "difficulty": 2, "mastery": 90}, {"name": "Trees", "difficulty": 4, "mastery": 30},
                        {"name": "Graphs", "difficulty": 5, "mastery": 20}, {"name": "Queues", "difficulty": 3, "mastery": 45}]},
            {"name": "Operating Systems", "difficulty": 4, "importance": 4, "target_marks": 80, "exam_date": str(today + timedelta(days=days_to_exam[1])),
             "topics": [{"name": "Virtual Memory", "difficulty": 5, "mastery": 35}, {"name": "Deadlocks", "difficulty": 4, "mastery": 50}]},
        ],
        "weekday_minutes": 180, "weekend_minutes": 240, "preferred_times": ["morning", "evening"],
        "default_level": 40, "target_marks": 85, "timezone": "Asia/Kolkata",
    }


@pytest.fixture
def planned(client, auth):
    headers, uid = auth
    r = client.post("/api/onboarding", json=onboarding_payload(), headers=headers)
    assert r.status_code == 201, r.text
    return headers, uid, r.json()
