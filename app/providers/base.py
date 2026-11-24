"""Provider abstraction shared by all voice-clone platforms."""
from __future__ import annotations

import base64
import json
import re
import secrets
import time
from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar

import httpx


class ProviderError(Exception):
    """Error raised by a provider; ``message`` is user-facing."""

    def __init__(self, message: str, *, status_code: int = 502, raw: Any = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.raw = raw


@dataclass
class Field:
    """A dynamic form field (TTS params / clone options / credentials)."""

    key: str
    label: str
    type: str = "text"  # slider | number | select | switch | text | textarea | password
    default: Any = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: list[dict[str, Any]] | None = None
    help: str = ""
    placeholder: str = ""
    required: bool = False
    secret: bool = False
    group: str = "basic"  # basic | advanced
    # only show when the voice model starts with one of these prefixes
    models: list[str] | None = None
    env: str | None = None  # env var used as fallback (credentials)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None and k != "env"}


def opts(*pairs: Any) -> list[dict[str, Any]]:
    """opts(("mp3", "MP3"), "wav") -> [{"value": "mp3", "label": "MP3"}, ...]"""
    out = []
    for p in pairs:
        if isinstance(p, (tuple, list)):
            out.append({"value": p[0], "label": p[1]})
        else:
            out.append({"value": p, "label": str(p)})
    return out


@dataclass
class RemoteVoice:
    voice_id: str
    name: str = ""
    status: str = "unknown"  # ready | training | failed | unknown
    model: str = ""
    demo_url: str = ""
    created_at: str = ""
    message: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CloneRequest:
    name: str
    model: str = ""
    voice_id: str = ""  # user supplied platform id (speaker id / custom id / prefix)
    audio: bytes | None = None
    audio_format: str = ""
    audio_url: str = ""
    transcript: str = ""
    demo_text: str = ""
    language: str = ""
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class CloneResult:
    voice_id: str
    status: str = "ready"
    model: str = ""
    demo_url: str = ""
    demo_audio: bytes | None = None
    demo_format: str = ""
    message: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SynthesisResult:
    audio: bytes
    format: str
    sample_rate: int | None = None
    duration_ms: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class BaseProvider:
    name: ClassVar[str] = ""
    label: ClassVar[str] = ""
    vendor: ClassVar[str] = ""
    description: ClassVar[str] = ""
    docs_url: ClassVar[str] = ""
    console_url: ClassVar[str] = ""
    color: ClassVar[str] = "#6366f1"
    # accepted reference-audio containers
    clone_audio_formats: ClassVar[list[str]] = ["wav", "mp3"]
    clone_tips: ClassVar[list[str]] = []
    # setup guide shown on the provider config page:
    # [{"title": str, "text": str, "links": [{"label": str, "url": str}]}]
    guide: ClassVar[list[dict[str, Any]]] = []
    capabilities: ClassVar[dict[str, bool]] = {
        "clone": True,
        "list": True,
        "delete": True,
        "query": True,
        "audio_url": False,
    }
    # [{"value": "model-id", "label": "...", "group": "...", "default": bool}]
    models: ClassVar[list[dict[str, Any]]] = []
    credential_fields: ClassVar[list[Field]] = []
    # how the "platform voice id" input of the clone form is presented
    voice_id_field: ClassVar[Field | None] = None
    clone_fields: ClassVar[list[Field]] = []
    tts_params: ClassVar[list[Field]] = []
    default_demo_text: ClassVar[str] = "你好，这是我的专属声音，很高兴认识你，欢迎体验声音复刻。"
    max_text_length: ClassVar[int] = 5000

    def __init__(self, creds: dict[str, Any], client: httpx.AsyncClient):
        self.creds = creds
        self.client = client

    # ----------------------------------------------------------------- meta
    @classmethod
    def default_model(cls) -> str:
        for m in cls.models:
            if m.get("default"):
                return m["value"]
        return cls.models[0]["value"] if cls.models else ""

    @classmethod
    def required_credentials(cls) -> list[list[str]]:
        """Alternative sets of credential keys; any satisfied set means configured."""
        return [[f.key for f in cls.credential_fields if f.required]]

    @classmethod
    def is_configured(cls, creds: dict[str, Any]) -> bool:
        return any(all(creds.get(k) for k in group) for group in cls.required_credentials())

    @classmethod
    def param_defaults(cls, model: str = "") -> dict[str, Any]:
        out = {}
        for f in cls.tts_params:
            if f.default is None:
                continue
            if f.models and model and not any(model.startswith(p) for p in f.models):
                continue
            out[f.key] = f.default
        return out

    @classmethod
    def meta(cls) -> dict[str, Any]:
        return {
            "name": cls.name,
            "label": cls.label,
            "vendor": cls.vendor,
            "description": cls.description,
            "docs_url": cls.docs_url,
            "console_url": cls.console_url,
            "color": cls.color,
            "capabilities": cls.capabilities,
            "models": cls.models,
            "default_model": cls.default_model(),
            "clone_audio_formats": cls.clone_audio_formats,
            "clone_tips": cls.clone_tips,
            "guide": cls.guide,
            "credential_fields": [f.to_dict() for f in cls.credential_fields],
            "voice_id_field": cls.voice_id_field.to_dict() if cls.voice_id_field else None,
            "clone_fields": [f.to_dict() for f in cls.clone_fields],
            "tts_params": [f.to_dict() for f in cls.tts_params],
            "default_demo_text": cls.default_demo_text,
            "max_text_length": cls.max_text_length,
        }

    # ------------------------------------------------------------- helpers
    def cred(self, key: str, default: str = "") -> str:
        val = self.creds.get(key)
        return str(val).strip() if val not in (None, "") else default

    @staticmethod
    def gen_id(prefix: str = "vd", length: int = 6) -> str:
        return f"{prefix}{time.strftime('%m%d%H%M')}{secrets.token_hex(length // 2)}"

    @staticmethod
    def slug(text: str, *, allowed: str = r"a-zA-Z0-9", max_len: int = 32, lower: bool = False) -> str:
        s = re.sub(rf"[^{allowed}]", "", text or "")
        if lower:
            s = s.lower()
        return s[:max_len]

    @staticmethod
    def b64(data: bytes) -> str:
        return base64.b64encode(data).decode()

    @staticmethod
    def data_uri(data: bytes, fmt: str) -> str:
        mime = {"mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4", "ogg": "audio/ogg"}.get(fmt, f"audio/{fmt}")
        return f"data:{mime};base64,{base64.b64encode(data).decode()}"

    @staticmethod
    def parse_json(resp: httpx.Response) -> Any:
        try:
            return resp.json()
        except (json.JSONDecodeError, ValueError):
            return None

    async def download(self, url: str) -> bytes:
        resp = await self.client.get(url, follow_redirects=True)
        if resp.status_code >= 400:
            raise ProviderError(f"下载音频失败 (HTTP {resp.status_code})")
        return resp.content

    @staticmethod
    def num(params: dict[str, Any], key: str, default: float, lo: float | None = None, hi: float | None = None) -> float:
        try:
            v = float(params.get(key, default))
        except (TypeError, ValueError):
            v = default
        if lo is not None:
            v = max(lo, v)
        if hi is not None:
            v = min(hi, v)
        return v

    # ---------------------------------------------------------- operations
    async def test(self) -> str:
        await self.list_voices()
        return "连接成功"

    async def clone(self, req: CloneRequest) -> CloneResult:  # pragma: no cover - abstract
        raise ProviderError("该平台暂不支持声音复刻", status_code=400)

    async def get_voice(self, voice_id: str, model: str = "", extra: dict | None = None) -> RemoteVoice | None:
        return None

    async def list_voices(self) -> list[RemoteVoice]:
        return []

    async def delete_voice(self, voice_id: str, model: str = "", extra: dict | None = None) -> None:
        raise ProviderError("该平台不支持通过 API 删除音色", status_code=400)

    async def synthesize(self, text: str, voice_id: str, model: str, params: dict[str, Any]) -> SynthesisResult:
        raise NotImplementedError
