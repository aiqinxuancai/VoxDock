"""Speech synthesis + generation history + OpenAI compatible endpoint."""
from __future__ import annotations

import base64
import json
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audio import ext_for, mime_for
from ..auth import require_auth
from ..db import get_session
from ..models import Generation
from ..services import storage
from ..services.tts import SHORTCUT_PARAMS, generation_to_dict, synthesize

router = APIRouter(tags=["合成"], dependencies=[Depends(require_auth)])


class TTSBody(BaseModel):
    voice: str | int = Field(..., description="音色：音色库 ID / 平台音色 ID / 音色名称 / provider:voice_id")
    text: str = Field(..., description="要合成的文本")
    provider: str | None = Field(None, description="平台（voice 为平台原始 ID 时可指定）")
    model: str | None = Field(None, description="覆盖音色绑定的模型")
    params: dict[str, Any] = Field(default_factory=dict, description="平台参数，见 GET /api/providers 的 tts_params")
    format: str | None = None
    speed: float | None = None
    volume: float | None = None
    pitch: float | None = None
    sample_rate: int | None = None
    emotion: str | None = None
    instruction: str | None = None
    language: str | None = None
    output: Literal["audio", "url", "base64"] = Field("audio", description="audio=直接返回音频；url/base64=返回 JSON")
    save: bool = Field(True, description="是否保存到历史记录")

    def merged_params(self) -> dict[str, Any]:
        shortcuts = {k: getattr(self, k) for k in SHORTCUT_PARAMS if getattr(self, k) is not None}
        return {**shortcuts, **(self.params or {})}


def _audio_response(result, gen, rv) -> Response:
    fmt = result.format
    headers = {
        "X-Voice-Provider": rv.provider,
        "X-Voice-Id": quote(rv.voice_id),
        "X-Elapsed-Ms": str(result.extra.get("elapsed_ms", "")),
        "Content-Disposition": f'inline; filename="voxdock-{gen.id if gen else "tts"}.{ext_for(fmt)}"',
    }
    if gen is not None:
        headers["X-Generation-Id"] = str(gen.id)
    if result.duration_ms:
        headers["X-Audio-Duration-Ms"] = str(result.duration_ms)
    return Response(content=result.audio, media_type=mime_for(fmt), headers=headers)


async def _run(session, body: TTSBody, source: str):
    save = body.save or body.output == "url"
    result, gen, rv = await synthesize(
        session, voice_ref=body.voice, text=body.text, params=body.merged_params(),
        provider=body.provider, model=body.model, save=save, source=source,
    )
    if body.output == "audio":
        return _audio_response(result, gen, rv)
    payload: dict[str, Any] = {
        "provider": rv.provider,
        "voice_id": rv.voice_id,
        "voice_name": rv.name,
        "format": result.format,
        "duration_ms": result.duration_ms,
        "elapsed_ms": result.extra.get("elapsed_ms"),
        "generation": generation_to_dict(gen) if gen else None,
        "audio_url": f"/api/generations/{gen.id}/audio" if gen else None,
    }
    if body.output == "base64":
        payload["audio_base64"] = base64.b64encode(result.audio).decode()
    return payload


@router.post("/api/tts", summary="合成语音（克隆音色）")
async def tts(body: TTSBody, request: Request, session: AsyncSession = Depends(get_session)):
    source = "web" if request.headers.get("x-voxdock-client") == "web" else "api"
    return await _run(session, body, source)


@router.get("/api/tts", summary="合成语音（GET，直接返回音频，便于嵌入/测试）")
async def tts_get(
    voice: str,
    text: str,
    provider: str | None = None,
    model: str | None = None,
    format: str | None = None,
    speed: float | None = None,
    volume: float | None = None,
    pitch: float | None = None,
    params: str | None = Query(None, description="JSON 格式的平台参数"),
    save: bool = True,
    session: AsyncSession = Depends(get_session),
):
    try:
        extra = json.loads(params) if params else {}
    except ValueError:
        raise HTTPException(status_code=400, detail="params 必须是 JSON") from None
    body = TTSBody(voice=voice, text=text, provider=provider, model=model, format=format, speed=speed,
                   volume=volume, pitch=pitch, params=extra, save=save)
    return await _run(session, body, "api")


# ------------------------------------------------------------ history
@router.get("/api/generations", summary="合成历史", tags=["历史"])
async def list_generations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    provider: str | None = None,
    voice_pk: int | None = None,
    q: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Generation)
    if provider:
        stmt = stmt.where(Generation.provider == provider)
    if voice_pk:
        stmt = stmt.where(Generation.voice_pk == voice_pk)
    if q:
        stmt = stmt.where(or_(Generation.text.ilike(f"%{q}%"), Generation.voice_name.ilike(f"%{q}%")))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await session.execute(
        stmt.order_by(Generation.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {"items": [generation_to_dict(g) for g in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/api/generations/{gid}/audio", summary="获取合成音频", tags=["历史"])
async def generation_audio(gid: int, download: bool = False, session: AsyncSession = Depends(get_session)):
    gen = await session.get(Generation, gid)
    if gen is None or not storage.exists(gen.audio_path):
        raise HTTPException(status_code=404, detail="音频不存在")
    ext = ext_for(gen.audio_format)
    return FileResponse(
        storage.abs_path(gen.audio_path),
        media_type=mime_for(gen.audio_format),
        filename=f"{gen.voice_name or 'voxdock'}-{gen.id}.{ext}",
        content_disposition_type="attachment" if download else "inline",
    )


@router.delete("/api/generations/{gid}", summary="删除历史记录", tags=["历史"])
async def delete_generation(gid: int, session: AsyncSession = Depends(get_session)):
    gen = await session.get(Generation, gid)
    if gen is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    storage.remove(gen.audio_path)
    await session.delete(gen)
    await session.commit()
    return {"ok": True}


@router.delete("/api/generations", summary="清空历史记录", tags=["历史"])
async def clear_generations(voice_pk: int | None = None, session: AsyncSession = Depends(get_session)):
    stmt = select(Generation.id, Generation.audio_path)
    if voice_pk:
        stmt = stmt.where(Generation.voice_pk == voice_pk)
    rows = (await session.execute(stmt)).all()
    for _, path in rows:
        storage.remove(path)
    ids = [r[0] for r in rows]
    if ids:
        await session.execute(delete(Generation).where(Generation.id.in_(ids)))
        await session.commit()
    return {"deleted": len(ids)}


# ------------------------------------------------------ OpenAI compatible
class OpenAISpeech(BaseModel):
    model: str | None = Field(None, description="忽略（由音色决定）；可填 provider 名强制平台")
    input: str
    voice: str
    response_format: str | None = Field(None, description="mp3 / wav / flac / opus ...")
    speed: float | None = None
    instructions: str | None = None


@router.post("/v1/audio/speech", summary="OpenAI 兼容：文本转语音", tags=["OpenAI 兼容"])
async def openai_speech(body: OpenAISpeech, session: AsyncSession = Depends(get_session)):
    from ..providers import PROVIDERS

    params: dict[str, Any] = {}
    if body.response_format and body.response_format not in ("pcm", "aac"):
        params["format"] = body.response_format
    if body.speed is not None:
        params["speed"] = body.speed
    if body.instructions:
        params["instruction"] = body.instructions
    provider = body.model if body.model in PROVIDERS else None
    tts_body = TTSBody(voice=body.voice, text=body.input, provider=provider, params=params, output="audio")
    return await _run(session, tts_body, "openai")
