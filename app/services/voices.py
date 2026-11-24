"""Voice library orchestration: clone, import, sync, refresh, delete."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audio import AudioError, detect_format, ensure_format, merge_clips
from ..config import get_settings
from ..db import session_factory
from ..models import Voice, utcnow
from ..providers import CloneRequest, ProviderError, RemoteVoice, get_provider_cls
from . import storage
from .providers import get_provider

log = logging.getLogger("voxdock.voices")
_bg_tasks: set[asyncio.Task] = set()


def voice_to_dict(v: Voice) -> dict[str, Any]:
    return {
        "id": v.id,
        "provider": v.provider,
        "voice_id": v.voice_id,
        "name": v.name,
        "description": v.description or "",
        "tags": v.tags or [],
        "status": v.status,
        "status_message": v.status_message or "",
        "model": v.model or "",
        "language": v.language or "",
        "source": v.source,
        "favorite": bool(v.favorite),
        "has_sample": storage.exists(v.sample_path),
        "sample_text": v.sample_text or "",
        "has_demo": storage.exists(v.demo_path) or bool(v.demo_url),
        "default_params": v.default_params or {},
        "extra": v.extra or {},
        "usage_count": v.usage_count or 0,
        "last_used_at": v.last_used_at.isoformat() if v.last_used_at else None,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "updated_at": v.updated_at.isoformat() if v.updated_at else None,
    }


async def find_voice(session: AsyncSession, provider: str, voice_id: str) -> Voice | None:
    res = await session.execute(select(Voice).where(Voice.provider == provider, Voice.voice_id == voice_id))
    return res.scalars().first()


async def _store_demo(voice: Voice, provider, *, data: bytes | None = None, fmt: str = "", url: str = "") -> None:
    """Persist demo audio locally (platform URLs usually expire)."""
    if url:
        voice.demo_url = url
    if data is None and url:
        try:
            data = await provider.download(url)
            fmt = detect_format(data, url.split("?")[0])
        except Exception as e:  # noqa: BLE001
            log.warning("download demo failed: %s", e)
            return
    if data:
        storage.remove(voice.demo_path)
        voice.demo_path = storage.save("demos", data, fmt if fmt and fmt != "unknown" else "mp3")


async def _ensure_supported(cls, data: bytes, fmt: str) -> tuple[bytes, str]:
    try:
        return await ensure_format(data, fmt, cls.clone_audio_formats)
    except AudioError as e:
        raise ProviderError(f"{cls.label} 仅支持 {'/'.join(cls.clone_audio_formats)} 格式；{e}", status_code=400) from e


async def prepare_reference(
    provider_name: str, files: list[tuple[bytes, str | None]]
) -> tuple[bytes, str, list[tuple[bytes, str]], dict[str, Any]]:
    """Validate reference clips and adapt them to the provider.

    Returns (audio, format, clips, info). When the provider accepts fewer clips than uploaded,
    the clips are merged locally in order with ``merge_gap_seconds`` of silence in between.
    """
    settings = get_settings()
    cls = get_provider_cls(provider_name)
    if len(files) > settings.max_reference_audios:
        raise ProviderError(f"参考音频最多 {settings.max_reference_audios} 段", status_code=400)
    clips: list[tuple[bytes, str]] = []
    for idx, (data, filename) in enumerate(files, 1):
        label = f"第 {idx} 段音频" if len(files) > 1 else "音频文件"
        if len(data) > settings.max_upload_mb * 1024 * 1024:
            raise ProviderError(f"{label}过大（上限 {settings.max_upload_mb}MB）", status_code=413)
        if len(data) < 1024:
            raise ProviderError(f"{label}过小或为空", status_code=400)
        fmt = detect_format(data, filename)
        if fmt == "unknown":
            raise ProviderError(f"{label}格式无法识别，请上传 wav / mp3 / m4a", status_code=400)
        clips.append((data, fmt))

    info: dict[str, Any] = {"reference_count": len(clips)}
    if len(clips) == 1:
        audio, fmt = await _ensure_supported(cls, *clips[0])
        return audio, fmt, [], info
    if len(clips) <= cls.max_reference_audios:
        converted = [await _ensure_supported(cls, d, f) for d, f in clips]
        return converted[0][0], converted[0][1], converted, info
    try:
        merged, duration_ms = await merge_clips(clips, settings.merge_gap_seconds)
    except AudioError as e:
        raise ProviderError(str(e), status_code=400) from e
    info.update(merged=True, merge_gap_seconds=settings.merge_gap_seconds, reference_duration_ms=duration_ms)
    audio, fmt = await _ensure_supported(cls, merged, "wav")
    return audio, fmt, [], info


async def clone_voice(
    session: AsyncSession,
    *,
    provider_name: str,
    name: str,
    model: str = "",
    voice_id: str = "",
    transcript: str = "",
    demo_text: str = "",
    description: str = "",
    tags: list[str] | None = None,
    options: dict[str, Any] | None = None,
    files: list[tuple[bytes, str | None]] | None = None,
    audio_url: str = "",
) -> Voice:
    cls = get_provider_cls(provider_name)
    if not cls.capabilities.get("clone"):
        raise ProviderError(f"{cls.label} 不支持声音复刻", status_code=400)
    name = (name or "").strip()
    if not name:
        raise ProviderError("请填写音色名称", status_code=400)
    files = [(d, n) for d, n in (files or []) if d]
    audio: bytes | None = None
    fmt = ""
    clips: list[tuple[bytes, str]] = []
    ref_info: dict[str, Any] = {}
    if files:
        audio, fmt, clips, ref_info = await prepare_reference(provider_name, files)
    elif audio_url:
        if not cls.capabilities.get("audio_url"):
            raise ProviderError(f"{cls.label} 不支持通过 URL 复刻，请上传音频文件", status_code=400)
    else:
        raise ProviderError("请上传参考音频", status_code=400)

    provider = await get_provider(session, provider_name)
    options = options or {}
    req = CloneRequest(
        name=name,
        model=model or cls.default_model(),
        voice_id=voice_id.strip(),
        audio=audio,
        audio_format=fmt,
        audio_url=audio_url.strip(),
        transcript=transcript.strip(),
        demo_text=demo_text.strip(),
        language=str(options.get("language") or ""),
        options=options,
        clips=clips,
    )
    result = await provider.clone(req)

    voice = await find_voice(session, provider_name, result.voice_id)
    if voice is None:
        voice = Voice(provider=provider_name, voice_id=result.voice_id)
        session.add(voice)
    voice.name = name
    voice.description = description or voice.description or ""
    voice.tags = tags if tags is not None else (voice.tags or [])
    voice.status = result.status
    voice.status_message = result.message or ""
    voice.model = result.model or req.model
    voice.language = req.language
    voice.source = "clone"
    voice.sample_text = req.transcript
    voice.extra = {**(voice.extra or {}), **result.extra, **ref_info, "options": options}
    stale = [] if ref_info.get("merged") else ["merged", "merge_gap_seconds", "reference_duration_ms"]
    if not ref_info:
        stale.append("reference_count")
    for key in stale:
        voice.extra.pop(key, None)
    if audio:
        storage.remove(voice.sample_path)
        voice.sample_path = storage.save("samples", audio, fmt)
    elif audio_url:
        voice.extra["sample_url"] = audio_url
    await _store_demo(voice, provider, data=result.demo_audio, fmt=result.demo_format, url=result.demo_url)
    await session.commit()
    await session.refresh(voice)
    if voice.status == "training":
        schedule_poll(voice.id)
    return voice


async def create_manual(session: AsyncSession, data: dict[str, Any]) -> Voice:
    provider_name = data["provider"]
    cls = get_provider_cls(provider_name)
    voice_id = (data.get("voice_id") or "").strip()
    if not voice_id:
        raise ProviderError("请填写平台音色 ID", status_code=400)
    if await find_voice(session, provider_name, voice_id):
        raise ProviderError("该音色已存在于音色库中", status_code=409)
    voice = Voice(
        provider=provider_name,
        voice_id=voice_id,
        name=(data.get("name") or voice_id).strip(),
        description=data.get("description") or "",
        tags=data.get("tags") or [],
        model=data.get("model") or cls.default_model(),
        status="ready",
        source="manual",
        default_params=data.get("default_params") or {},
    )
    session.add(voice)
    await session.commit()
    await session.refresh(voice)
    return voice


def _apply_remote(voice: Voice, rv: RemoteVoice) -> None:
    if rv.status != "unknown" or voice.status == "unknown":
        voice.status = rv.status
    voice.status_message = rv.message or voice.status_message or ""
    if rv.model and not voice.model:
        voice.model = rv.model
    if rv.extra:
        voice.extra = {**(voice.extra or {}), **{k: v for k, v in rv.extra.items() if v is not None}}


async def refresh_voice(session: AsyncSession, voice: Voice) -> Voice:
    provider = await get_provider(session, voice.provider)
    rv = await provider.get_voice(voice.voice_id, voice.model, voice.extra or {})
    if rv is None:
        if voice.status == "unknown":
            voice.status_message = "平台暂未返回该音色信息"
    else:
        _apply_remote(voice, rv)
        if rv.demo_url and (rv.demo_url != voice.demo_url or not storage.exists(voice.demo_path)):
            await _store_demo(voice, provider, url=rv.demo_url)
    voice.updated_at = utcnow()
    await session.commit()
    await session.refresh(voice)
    return voice


async def sync_provider(session: AsyncSession, provider_name: str) -> dict[str, int]:
    provider = await get_provider(session, provider_name)
    remote = await provider.list_voices()
    added = updated = 0
    for rv in remote:
        if not rv.voice_id:
            continue
        voice = await find_voice(session, provider_name, rv.voice_id)
        if voice is None:
            voice = Voice(
                provider=provider_name,
                voice_id=rv.voice_id,
                name=rv.name or rv.voice_id,
                model=rv.model or provider.default_model(),
                status=rv.status,
                status_message=rv.message,
                source="import",
                extra=rv.extra,
            )
            session.add(voice)
            added += 1
        else:
            _apply_remote(voice, rv)
            updated += 1
        if rv.demo_url and not storage.exists(voice.demo_path):
            voice.demo_url = rv.demo_url
    await session.commit()
    return {"added": added, "updated": updated, "total": len(remote)}


async def delete_voice(session: AsyncSession, voice: Voice, *, remote: bool = False, force: bool = False) -> None:
    if remote:
        cls = get_provider_cls(voice.provider)
        if not cls.capabilities.get("delete"):
            raise ProviderError(f"{cls.label} 不支持通过 API 删除平台音色，可仅从本地移除", status_code=400)
        try:
            provider = await get_provider(session, voice.provider, require_enabled=False)
            await provider.delete_voice(voice.voice_id, voice.model, voice.extra or {})
        except ProviderError:
            if not force:
                raise
    storage.remove(voice.sample_path)
    storage.remove(voice.demo_path)
    await session.delete(voice)
    await session.commit()


async def voice_stats(session: AsyncSession) -> dict[str, Any]:
    res = await session.execute(select(Voice.provider, func.count()).group_by(Voice.provider))
    return {p: c for p, c in res.all()}


# ------------------------------------------------------- background polling
def schedule_poll(voice_pk: int, *, interval: float = 6.0, attempts: int = 50) -> None:
    try:
        task = asyncio.get_running_loop().create_task(_poll(voice_pk, interval, attempts))
    except RuntimeError:
        return
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


async def _poll(voice_pk: int, interval: float, attempts: int) -> None:
    for _ in range(attempts):
        await asyncio.sleep(interval)
        try:
            async with session_factory()() as session:
                voice = await session.get(Voice, voice_pk)
                if voice is None or voice.status != "training":
                    return
                await refresh_voice(session, voice)
                if voice.status != "training":
                    return
        except ProviderError as e:
            log.info("poll voice %s: %s", voice_pk, e.message)
        except Exception:  # noqa: BLE001
            log.exception("poll voice %s failed", voice_pk)
            return
