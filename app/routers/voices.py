"""Voice library endpoints."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audio import mime_for
from ..auth import require_auth
from ..db import get_session
from ..models import Voice
from ..providers import get_provider_cls
from ..services import storage
from ..services import voices as svc

router = APIRouter(prefix="/api/voices", tags=["音色"], dependencies=[Depends(require_auth)])


class ManualVoice(BaseModel):
    provider: str
    voice_id: str
    name: str = ""
    model: str = ""
    description: str = ""
    tags: list[str] = []
    default_params: dict[str, Any] = {}


class VoicePatch(BaseModel):
    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    favorite: bool | None = None
    model: str | None = None
    default_params: dict[str, Any] | None = None


async def _get(session: AsyncSession, pk: int) -> Voice:
    voice = await session.get(Voice, pk)
    if voice is None:
        raise HTTPException(status_code=404, detail="音色不存在")
    return voice


@router.get("", summary="音色列表")
async def list_voices(
    provider: str | None = None,
    status: str | None = None,
    q: str | None = Query(None, description="按名称/ID/标签搜索"),
    favorite: bool | None = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Voice)
    if provider:
        stmt = stmt.where(Voice.provider == provider)
    if status:
        stmt = stmt.where(Voice.status == status)
    if favorite is not None:
        stmt = stmt.where(Voice.favorite == favorite)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Voice.name.ilike(like), Voice.voice_id.ilike(like), Voice.description.ilike(like)))
    stmt = stmt.order_by(Voice.favorite.desc(), Voice.updated_at.desc())
    rows = (await session.execute(stmt)).scalars().all()
    return {"items": [svc.voice_to_dict(v) for v in rows]}


@router.post("", summary="手动添加音色（已有的平台音色 ID / 系统音色）")
async def add_voice(body: ManualVoice, session: AsyncSession = Depends(get_session)):
    get_provider_cls(body.provider)
    return svc.voice_to_dict(await svc.create_manual(session, body.model_dump()))


@router.post("/clone", summary="上传参考音频复刻新音色")
async def clone_voice(
    provider: str = Form(..., description="volcengine / aliyun / minimax / zhipu"),
    name: str = Form(..., description="音色显示名称"),
    model: str = Form("", description="目标模型，留空使用平台默认"),
    voice_id: str = Form("", description="平台音色 ID / 前缀，留空自动生成（火山必填 S_xxx）"),
    transcript: str = Form("", description="参考音频对应文本（可选）"),
    demo_text: str = Form("", description="试听文本（可选）"),
    description: str = Form(""),
    tags: str = Form("", description="逗号分隔"),
    options: str = Form("{}", description="平台特定选项 JSON"),
    audio_url: str = Form("", description="公网音频 URL（部分平台支持）"),
    file: list[UploadFile] | None = File(
        None,
        description="参考音频文件，可重复传多个（-F file=@a.wav -F file=@b.wav）。"
        "平台只支持单条时按顺序本地合并，每段间隔 2 秒",
    ),
    session: AsyncSession = Depends(get_session),
):
    try:
        opts = json.loads(options or "{}")
        if not isinstance(opts, dict):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="options 必须是 JSON 对象") from None
    files = [(await f.read(), f.filename) for f in (file or [])]
    voice = await svc.clone_voice(
        session,
        provider_name=provider,
        name=name,
        model=model,
        voice_id=voice_id,
        transcript=transcript,
        demo_text=demo_text,
        description=description,
        tags=[t.strip() for t in tags.replace("，", ",").split(",") if t.strip()],
        options=opts,
        files=files,
        audio_url=audio_url,
    )
    return svc.voice_to_dict(voice)


@router.get("/{pk}", summary="音色详情")
async def get_voice(pk: int, session: AsyncSession = Depends(get_session)):
    return svc.voice_to_dict(await _get(session, pk))


@router.patch("/{pk}", summary="编辑音色")
async def patch_voice(pk: int, body: VoicePatch, session: AsyncSession = Depends(get_session)):
    voice = await _get(session, pk)
    for key, val in body.model_dump(exclude_unset=True).items():
        if val is not None:
            setattr(voice, key, val.strip() if isinstance(val, str) else val)
    await session.commit()
    await session.refresh(voice)
    return svc.voice_to_dict(voice)


@router.delete("/{pk}", summary="删除音色")
async def delete_voice(
    pk: int,
    remote: bool = Query(False, description="同时删除平台上的音色"),
    force: bool = Query(False, description="平台删除失败时仍删除本地记录"),
    session: AsyncSession = Depends(get_session),
):
    await svc.delete_voice(session, await _get(session, pk), remote=remote, force=force)
    return {"ok": True}


@router.post("/{pk}/refresh", summary="刷新音色状态")
async def refresh_voice(pk: int, session: AsyncSession = Depends(get_session)):
    return svc.voice_to_dict(await svc.refresh_voice(session, await _get(session, pk)))


def _file(rel: str, name: str) -> FileResponse:
    fmt = rel.rsplit(".", 1)[-1]
    return FileResponse(storage.abs_path(rel), media_type=mime_for(fmt), filename=f"{name}.{fmt}",
                        content_disposition_type="inline")


@router.get("/{pk}/sample", summary="参考音频")
async def voice_sample(pk: int, session: AsyncSession = Depends(get_session)):
    voice = await _get(session, pk)
    if not storage.exists(voice.sample_path):
        if (voice.extra or {}).get("sample_url"):
            return RedirectResponse(voice.extra["sample_url"])
        raise HTTPException(status_code=404, detail="无参考音频")
    return _file(voice.sample_path, f"{voice.name}-sample")


@router.get("/{pk}/demo", summary="平台试听音频")
async def voice_demo(pk: int, session: AsyncSession = Depends(get_session)):
    voice = await _get(session, pk)
    if storage.exists(voice.demo_path):
        return _file(voice.demo_path, f"{voice.name}-demo")
    if voice.demo_url:
        return RedirectResponse(voice.demo_url)
    raise HTTPException(status_code=404, detail="无试听音频")
