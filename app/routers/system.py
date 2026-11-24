"""Auth, system info and API key management."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audio import ffmpeg_available
from ..auth import (
    SESSION_COOKIE,
    auth_enabled,
    check_password,
    current_identity,
    generate_api_key,
    hash_key,
    make_session_token,
    require_admin,
    require_auth,
)
from ..config import APP_NAME, APP_VERSION, get_settings
from ..db import get_session
from ..models import ApiKey, Generation, Voice

router = APIRouter(prefix="/api", tags=["系统"])


class LoginBody(BaseModel):
    password: str


@router.get("/auth/status", summary="登录状态")
async def auth_status(request: Request, session: AsyncSession = Depends(get_session)):
    ident = await current_identity(request, session)
    return {"auth_enabled": auth_enabled(), "authenticated": ident is not None, "identity": ident}


@router.post("/auth/login", summary="管理员登录")
async def login(body: LoginBody, response: Response):
    if not auth_enabled():
        return {"ok": True}
    if not check_password(body.password):
        await asyncio.sleep(0.8)
        raise HTTPException(status_code=401, detail="密码错误")
    response.set_cookie(
        SESSION_COOKIE,
        make_session_token(),
        max_age=get_settings().session_days * 86400,
        httponly=True,
        samesite="lax",
    )
    return {"ok": True}


@router.post("/auth/logout", summary="退出登录")
async def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@router.get("/system", summary="系统信息与统计", dependencies=[Depends(require_auth)])
async def system_info(session: AsyncSession = Depends(get_session)):
    voices = (await session.execute(select(Voice.provider, func.count()).group_by(Voice.provider))).all()
    gen_row = (await session.execute(
        select(func.count(), func.coalesce(func.sum(func.length(Generation.text)), 0),
               func.coalesce(func.sum(Generation.duration_ms), 0))
    )).one()
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "auth_enabled": auth_enabled(),
        "ffmpeg": ffmpeg_available(),
        "max_reference_audios": get_settings().max_reference_audios,
        "merge_gap_seconds": get_settings().merge_gap_seconds,
        "max_upload_mb": get_settings().max_upload_mb,
        "stats": {
            "voices": sum(c for _, c in voices),
            "voices_by_provider": {p: c for p, c in voices},
            "generations": gen_row[0],
            "characters": int(gen_row[1] or 0),
            "audio_ms": int(gen_row[2] or 0),
        },
    }


# ------------------------------------------------------------- API keys
class KeyBody(BaseModel):
    name: str = Field(default="default", max_length=64)


def _key_dict(k: ApiKey) -> dict:
    return {
        "id": k.id,
        "name": k.name,
        "prefix": k.prefix,
        "created_at": k.created_at.isoformat() if k.created_at else None,
        "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
    }


@router.get("/keys", summary="API Key 列表", tags=["API Key"], dependencies=[Depends(require_admin)])
async def list_keys(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(ApiKey).order_by(ApiKey.id.desc()))).scalars().all()
    return {"items": [_key_dict(k) for k in rows], "static_keys": len(get_settings().static_api_keys())}


@router.post("/keys", summary="创建 API Key（明文仅返回一次）", tags=["API Key"], dependencies=[Depends(require_admin)])
async def create_key(body: KeyBody, session: AsyncSession = Depends(get_session)):
    key = generate_api_key()
    row = ApiKey(name=body.name.strip() or "default", key_hash=hash_key(key), prefix=key[:10])
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return {**_key_dict(row), "key": key}


@router.delete("/keys/{key_id}", summary="删除 API Key", tags=["API Key"], dependencies=[Depends(require_admin)])
async def delete_key(key_id: int, session: AsyncSession = Depends(get_session)):
    row = await session.get(ApiKey, key_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Key 不存在")
    await session.delete(row)
    await session.commit()
    return {"ok": True}
