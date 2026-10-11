"""Thin, cost-aware AI client.

Guard rails: (1) the planner never needs it; (2) identical prompts hit the DB cache; (3) concurrent identical requests
are de-duplicated with a per-key lock; (4) per-user daily call cap; (5) circuit breaker after repeated failures;
(6) small prompts, small max_tokens. Any failure raises AIUnavailable and callers fall back to rule-based output.
"""
import hashlib
import json
import threading
import time
from datetime import datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from .. import models as m
from ..config import get_settings
from ..timeutil import local_now

UNAVAILABLE_MESSAGE = "AI recommendations are temporarily unavailable. Your normal study planner is still working."


class AIUnavailable(Exception):
    pass


_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_failures = {"count": 0, "open_until": 0.0}


def is_enabled() -> bool:
    return bool(get_settings().ai_api_key)


def _key(*parts: str) -> str:
    return hashlib.sha256("||".join(parts).encode()).hexdigest()


def _call_provider(system: str, prompt: str, max_tokens: int) -> str:
    s = get_settings()
    if s.ai_provider == "openai":
        base = (s.ai_base_url or "https://api.openai.com/v1").rstrip("/")
        r = httpx.post(f"{base}/chat/completions", timeout=20,
                       headers={"Authorization": f"Bearer {s.ai_api_key}"},
                       json={"model": s.ai_model, "max_tokens": max_tokens, "temperature": 0.2,
                             "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    r = httpx.post("https://api.anthropic.com/v1/messages", timeout=20,
                   headers={"x-api-key": s.ai_api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                   json={"model": s.ai_model, "max_tokens": max_tokens, "system": system,
                         "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")


def complete(db: Session, user: m.User, *, system: str, prompt: str, max_tokens: int = 300, use_cache: bool = True) -> tuple[str, bool]:
    """Returns (text, from_cache). Raises AIUnavailable on any problem."""
    s = get_settings()
    if not is_enabled():
        raise AIUnavailable("not configured")
    if time.time() < _failures["open_until"]:
        raise AIUnavailable("circuit open")
    key = _key(s.ai_model, system, prompt)
    ttl = timedelta(hours=s.ai_cache_hours)

    def cached() -> str | None:
        row = db.get(m.AICache, key)
        if row and use_cache and datetime.utcnow() - row.created_at < ttl:
            return row.response
        return None

    hit = cached()
    if hit is not None:
        return hit, True
    with _locks_guard:
        lock = _locks.setdefault(key, threading.Lock())
    with lock:                                   # request de-duplication
        db.expire_all()
        hit = cached()
        if hit is not None:
            return hit, True
        today = local_now(user.preferences.timezone).date()
        usage = db.query(m.AIUsage).filter_by(user_id=user.id, day=today).first()
        if usage and usage.calls >= s.ai_daily_limit_per_user:
            raise AIUnavailable("daily AI limit reached")
        try:
            text = _call_provider(system, prompt, max_tokens)
            _failures["count"] = 0
        except Exception as exc:                 # network, auth, quota, malformed response ...
            _failures["count"] += 1
            if _failures["count"] >= 3:
                _failures["open_until"] = time.time() + 60
            raise AIUnavailable(str(exc)[:120]) from exc
        if usage is None:
            usage = m.AIUsage(user_id=user.id, day=today, calls=0)
            db.add(usage)
        usage.calls += 1
        existing = db.get(m.AICache, key)
        if existing:
            existing.response, existing.created_at = text, datetime.utcnow()
        else:
            db.add(m.AICache(key=key, response=text))
        db.flush()
        return text, False


def extract_json(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1:] if "\n" in text else text
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no json")
    end = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[start:end + 1])


def usage_today(db: Session, user: m.User) -> dict:
    s = get_settings()
    today = local_now(user.preferences.timezone).date()
    usage = db.query(m.AIUsage).filter_by(user_id=user.id, day=today).first()
    return {"enabled": is_enabled(), "used": usage.calls if usage else 0, "limit": s.ai_daily_limit_per_user}
