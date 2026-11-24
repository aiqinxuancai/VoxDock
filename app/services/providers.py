"""Provider credential storage & instantiation."""
from __future__ import annotations

import os
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ProviderConfig
from ..providers import PROVIDERS, BaseProvider, ProviderError, get_provider_cls
from .http import get_client

MASK = "••••"


def mask(value: str) -> str:
    value = str(value or "")
    if not value:
        return ""
    if len(value) <= 8:
        return MASK
    return f"{value[:3]}{MASK}{value[-4:]}"


async def _row(session: AsyncSession, name: str) -> ProviderConfig | None:
    return await session.get(ProviderConfig, name)


async def resolve_credentials(session: AsyncSession, name: str) -> tuple[dict[str, Any], dict[str, str], bool]:
    """Return (values, sources, enabled). DB values win over env vars, env over defaults."""
    cls = get_provider_cls(name)
    row = await _row(session, name)
    stored = dict(row.values or {}) if row else {}
    values: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for f in cls.credential_fields:
        if stored.get(f.key) not in (None, ""):
            values[f.key], sources[f.key] = stored[f.key], "db"
        elif f.env and os.environ.get(f.env):
            values[f.key], sources[f.key] = os.environ[f.env], "env"
        elif f.default not in (None, ""):
            values[f.key], sources[f.key] = f.default, "default"
        else:
            values[f.key], sources[f.key] = "", ""
    return values, sources, (row.enabled if row else True)


async def provider_summary(session: AsyncSession, name: str) -> dict[str, Any]:
    cls = get_provider_cls(name)
    values, _sources, enabled = await resolve_credentials(session, name)
    return {**cls.meta(), "configured": cls.is_configured(values), "enabled": enabled}


async def all_summaries(session: AsyncSession) -> list[dict[str, Any]]:
    return [await provider_summary(session, n) for n in PROVIDERS]


async def public_config(session: AsyncSession, name: str) -> dict[str, Any]:
    cls = get_provider_cls(name)
    values, sources, enabled = await resolve_credentials(session, name)
    out = {}
    for f in cls.credential_fields:
        v = values.get(f.key, "")
        out[f.key] = mask(v) if f.secret else v
    return {"values": out, "sources": sources, "enabled": enabled, "configured": cls.is_configured(values)}


async def update_config(session: AsyncSession, name: str, values: dict[str, Any], enabled: bool | None) -> None:
    cls = get_provider_cls(name)
    row = await _row(session, name)
    if row is None:
        row = ProviderConfig(provider=name, values={}, enabled=True)
        session.add(row)
    stored = dict(row.values or {})
    known = {f.key: f for f in cls.credential_fields}
    for key, val in (values or {}).items():
        f = known.get(key)
        if f is None:
            continue
        if val is None or (isinstance(val, str) and not val.strip()):
            stored.pop(key, None)
        elif f.secret and MASK in str(val):
            continue  # unchanged masked value
        else:
            stored[key] = str(val).strip()
    row.values = stored
    if enabled is not None:
        row.enabled = enabled
    await session.commit()


async def get_provider(session: AsyncSession, name: str, *, require_enabled: bool = True) -> BaseProvider:
    cls = get_provider_cls(name)
    values, _sources, enabled = await resolve_credentials(session, name)
    if require_enabled and not enabled:
        raise ProviderError(f"{cls.label} 已停用，请在「平台配置」中启用", status_code=400)
    if not cls.is_configured(values):
        raise ProviderError(f"{cls.label} 尚未配置密钥，请先在「平台配置」中填写", status_code=400)
    return cls(values, get_client())
