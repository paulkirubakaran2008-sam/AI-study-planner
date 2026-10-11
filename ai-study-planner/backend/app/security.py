import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, joinedload

from . import models as m
from .config import get_settings
from .database import get_db

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except ValueError:
        return False


def create_token(user_id: int) -> str:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=s.access_token_minutes)
    return jwt.encode({"sub": str(user_id), "exp": exp}, s.secret_key, algorithm="HS256")


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)) -> m.User:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    try:
        payload = jwt.decode(creds.credentials, get_settings().secret_key, algorithms=["HS256"])
        uid = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired. Please sign in again.")
    user = db.query(m.User).options(joinedload(m.User.preferences)).filter(m.User.id == uid).first()
    if not user or user.preferences is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not found")
    return user


class RateLimiter:
    """Tiny in-memory sliding window limiter (per process). Enough to blunt password guessing on a free tier."""

    def __init__(self, limit: int, window: int):
        self.limit, self.window, self.hits = limit, window, defaultdict(deque)

    def __call__(self, request: Request):
        ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
        now, q = time.time(), self.hits[ip]
        while q and q[0] < now - self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Please wait a minute and try again.")
        q.append(now)


auth_limiter = RateLimiter(15, 60)
demo_limiter = RateLimiter(10, 60)
