"""Speech synthesis orchestration + generation history."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audio import estimate_duration_ms
from ..config import get_settings
from ..models import Generation, Voice, utcnow
from ..providers import PROVIDERS, ProviderError, SynthesisResult, get_provider_cls
from . import storage
from .providers import get_provider

SHORTCUT_PARAMS = ("format", "speed", "volume", "pitch", "sample_rate", "emotion", "instruction", "language")


@dataclass
class ResolvedVoice:
    provider: str
    voice_id: str
    name: str
    model: str
    default_params: dict[str, Any]
    record: Voice | None = None


async def resolve_voice(session: AsyncSession, ref: Any, provider: str | None = None, model: str | None = None) -> ResolvedVoice:
    """Resolve a voice reference.

    Accepts: library id (``12``), ``provider:voice_id``, a platform voice id, or an exact voice name.
    Unknown ``provider:voice_id`` pairs are used ad-hoc (e.g. platform system voices).
    """
    ref_s = str(ref).strip()
    if not ref_s:
        raise ProviderError("请指定音色 voice", status_code=400)
    voice: Voice | None = None
    if ref_s.isdigit() and not provider:
        voice = await session.get(Voice, int(ref_s))
    if voice is None and ":" in ref_s and ref_s.split(":", 1)[0] in PROVIDERS:
        provider, ref_s = ref_s.split(":", 1)
    if voice is None:
        stmt = select(Voice).where(or_(Voice.voice_id == ref_s, Voice.name == ref_s))
        if provider:
            stmt = stmt.where(Voice.provider == provider)
        rows = (await session.execute(stmt)).scalars().all()
        voice = next((v for v in rows if v.voice_id == ref_s), rows[0] if rows else None)
    if voice is not None:
        return ResolvedVoice(voice.provider, voice.voice_id, voice.name, model or voice.model or "",
                             dict(voice.default_params or {}), voice)
    if provider:
        cls = get_provider_cls(provider)
        return ResolvedVoice(provider, ref_s, ref_s, model or cls.default_model(), {})
    raise ProviderError(f"未找到音色: {ref}（可使用 音色库ID、平台音色ID 或 provider:voice_id）", status_code=404)


def merge_params(cls, model: str, *layers: dict[str, Any] | None) -> dict[str, Any]:
    params = cls.param_defaults(model)
    for layer in layers:
        for k, v in (layer or {}).items():
            if v is not None:
                params[k] = v
    # unsupported output formats fall back to the provider default instead of failing upstream
    for f in cls.tts_params:
        if f.key == "format" and f.options and (not f.models or any(model.startswith(p) for p in f.models)):
            allowed = [o["value"] for o in f.options]
            aliases = {"ogg": "ogg_opus" if "ogg_opus" in allowed else "opus", "opus": "ogg_opus" if "ogg_opus" in allowed else "opus"}
            fmt = params.get("format")
            if fmt not in allowed:
                fmt = aliases.get(str(fmt), fmt)
                params["format"] = fmt if fmt in allowed else f.default
    return params


def generation_to_dict(g: Generation) -> dict[str, Any]:
    return {
        "id": g.id,
        "voice_pk": g.voice_pk,
        "provider": g.provider,
        "voice_id": g.voice_id,
        "voice_name": g.voice_name,
        "model": g.model,
        "text": g.text,
        "params": g.params or {},
        "format": g.audio_format,
        "size_bytes": g.size_bytes,
        "duration_ms": g.duration_ms,
        "elapsed_ms": g.elapsed_ms,
        "source": g.source,
        "created_at": g.created_at.isoformat() if g.created_at else None,
        "audio_url": f"/api/generations/{g.id}/audio",
    }


async def synthesize(
    session: AsyncSession,
    *,
    voice_ref: Any,
    text: str,
    params: dict[str, Any] | None = None,
    provider: str | None = None,
    model: str | None = None,
    save: bool = True,
    source: str = "api",
) -> tuple[SynthesisResult, Generation | None, ResolvedVoice]:
    text = (text or "").strip()
    if not text:
        raise ProviderError("合成文本不能为空", status_code=400)
    rv = await resolve_voice(session, voice_ref, provider, model)
    cls = get_provider_cls(rv.provider)
    limit = min(cls.max_text_length, get_settings().max_text_length)
    if len(text) > limit:
        raise ProviderError(f"文本过长：{len(text)} 字符，{cls.label} 单次上限 {limit} 字符", status_code=400)
    if rv.record is not None and rv.record.status == "failed":
        raise ProviderError("该音色复刻失败，无法用于合成", status_code=400)

    merged = merge_params(cls, rv.model, rv.default_params, params)
    impl = await get_provider(session, rv.provider)
    t0 = time.perf_counter()
    result = await impl.synthesize(text, rv.voice_id, rv.model, merged)
    elapsed = int((time.perf_counter() - t0) * 1000)
    if result.duration_ms is None:
        result.duration_ms = estimate_duration_ms(result.audio, result.format)

    gen: Generation | None = None
    if save:
        gen = Generation(
            voice_pk=rv.record.id if rv.record else None,
            provider=rv.provider,
            voice_id=rv.voice_id,
            voice_name=rv.name,
            model=str(merged.get("model") or rv.model or ""),
            text=text,
            params=merged,
            audio_path=storage.save("generations", result.audio, result.format),
            audio_format=result.format,
            size_bytes=len(result.audio),
            duration_ms=result.duration_ms,
            elapsed_ms=elapsed,
            source=source,
        )
        session.add(gen)
    if rv.record is not None:
        rv.record.usage_count = (rv.record.usage_count or 0) + 1
        rv.record.last_used_at = utcnow()
        if rv.record.status in ("training", "unknown"):
            rv.record.status, rv.record.status_message = "ready", "合成成功"
    await session.commit()
    if gen is not None:
        await session.refresh(gen)
    result.extra["elapsed_ms"] = elapsed
    return result, gen, rv
