"""Authentication: admin session cookie + API keys."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import get_session
from .models import ApiKey, utcnow

SESSION_COOKIE = "voxdock_session"


def auth_enabled() -> bool:
    return bool(get_settings().admin_password)


def _sign(payload: str) -> str:
    key = get_settings().resolved_secret().encode()
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()


def make_session_token() -> str:
    payload = f"admin.{int(time.time())}"
    return f"{payload}.{_sign(payload)}"


def verify_session_token(token: str | None) -> bool:
    if not token or token.count(".") != 2:
        return False
    role, ts, sig = token.split(".")
    payload = f"{role}.{ts}"
    if not hmac.compare_digest(sig, _sign(payload)):
        return False
    try:
        age = time.time() - int(ts)
    except ValueError:
        return False
    return 0 <= age <= get_settings().session_days * 86400


def check_password(password: str) -> bool:
    expected = get_settings().admin_password
    return bool(expected) and hmac.compare_digest(password.encode(), expected.encode())


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> str:
    return "vd-" + secrets.token_urlsafe(32)


def extract_api_key(request: Request) -> str | None:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return request.headers.get("x-api-key") or request.query_params.get("api_key") or None


async def validate_api_key(session: AsyncSession, key: str) -> bool:
    if key in get_settings().static_api_keys():
        return True
    row = (await session.execute(select(ApiKey).where(ApiKey.key_hash == hash_key(key)))).scalars().first()
    if row is None:
        return False
    row.last_used_at = utcnow()
    await session.commit()
    return True


async def current_identity(request: Request, session: AsyncSession) -> str | None:
    if not auth_enabled():
        return "open"
    if verify_session_token(request.cookies.get(SESSION_COOKIE)):
        return "session"
    key = extract_api_key(request)
    if key and await validate_api_key(session, key):
        return "api_key"
    return None


async def require_auth(request: Request, session: AsyncSession = Depends(get_session)) -> str:
    ident = await current_identity(request, session)
    if ident is None:
        raise HTTPException(status_code=401, detail="未登录或 API Key 无效")
    return ident


async def require_admin(request: Request, session: AsyncSession = Depends(get_session)) -> str:
    """Admin-only routes (credentials, API keys): session or open mode, not API keys."""
    if not auth_enabled():
        return "open"
    if verify_session_token(request.cookies.get(SESSION_COOKIE)):
        return "session"
    raise HTTPException(status_code=401 if not extract_api_key(request) else 403, detail="需要管理员登录")
