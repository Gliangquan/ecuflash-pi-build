import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Header, HTTPException
from sqlalchemy import text

from app.db import get_conn
from app.settings import settings


TOKEN_TTL_DAYS = 30


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def future_str(days: int = TOKEN_TTL_DAYS) -> str:
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def hash_password(password: str) -> str:
    raw = f"{settings.auth_password_salt}:{password}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash


def generate_token() -> str:
    return secrets.token_hex(32)


def parse_bearer_token(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="missing authorization header")
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise HTTPException(status_code=401, detail="invalid authorization header")
    token = authorization[len(prefix):].strip()
    if not token:
        raise HTTPException(status_code=401, detail="empty token")
    return token


def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    token = parse_bearer_token(authorization)
    sql = text(
        """
        SELECT
            u.id,
            u.phone,
            u.name,
            u.status,
            u.is_admin,
            u.auth_end_at,
            u.device_id,
            u.device_name,
            u.device_bound_at,
            u.created_at,
            u.updated_at,
            u.last_login_at,
            s.token,
            s.expired_at
        FROM app_session s
        JOIN app_user u ON u.id = s.user_id
        WHERE s.token = :token
          AND u.status = 'enabled'
          AND s.expired_at > NOW()
        LIMIT 1
        """
    )
    with get_conn() as conn:
        row = conn.execute(sql, {"token": token}).mappings().first()
        if not row:
            raise HTTPException(status_code=401, detail="session expired or invalid")
        conn.execute(
            text("UPDATE app_session SET last_seen_at = :now WHERE token = :token"),
            {"now": now_str(), "token": token},
        )
        conn.commit()
    return dict(row)


def require_admin(user: dict) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="admin required")
    return user
