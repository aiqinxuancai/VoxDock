"""Provider metadata, credentials and connectivity."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import require_admin, require_auth
from ..db import get_session
from ..providers import get_provider_cls
from ..services import providers as svc
from ..services.voices import sync_provider

router = APIRouter(prefix="/api/providers", tags=["平台"])


class ConfigBody(BaseModel):
    values: dict[str, Any] = {}
    enabled: bool | None = None


@router.get("", summary="平台列表（含参数定义）", dependencies=[Depends(require_auth)])
async def list_providers(session: AsyncSession = Depends(get_session)):
    return {"items": await svc.all_summaries(session)}


@router.get("/{name}", summary="平台详情", dependencies=[Depends(require_auth)])
async def get_provider(name: str, session: AsyncSession = Depends(get_session)):
    return await svc.provider_summary(session, name)


@router.get("/{name}/config", summary="读取平台配置（密钥脱敏）", dependencies=[Depends(require_admin)])
async def get_config(name: str, session: AsyncSession = Depends(get_session)):
    get_provider_cls(name)
    return await svc.public_config(session, name)


@router.put("/{name}/config", summary="更新平台配置", dependencies=[Depends(require_admin)])
async def put_config(name: str, body: ConfigBody, session: AsyncSession = Depends(get_session)):
    await svc.update_config(session, name, body.values, body.enabled)
    return await svc.public_config(session, name)


@router.post("/{name}/test", summary="测试连接", dependencies=[Depends(require_admin)])
async def test_provider(name: str, session: AsyncSession = Depends(get_session)):
    provider = await svc.get_provider(session, name, require_enabled=False)
    return {"ok": True, "message": await provider.test()}


@router.post("/{name}/sync", summary="从平台同步音色到音色库", dependencies=[Depends(require_auth)])
async def sync(name: str, session: AsyncSession = Depends(get_session)):
    return await sync_provider(session, name)
