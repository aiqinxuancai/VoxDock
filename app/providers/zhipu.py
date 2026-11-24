"""智谱 BigModel · GLM-TTS 音色复刻."""
from __future__ import annotations

import re
import uuid
from typing import Any

from .base import BaseProvider, CloneRequest, CloneResult, Field, ProviderError, RemoteVoice, SynthesisResult, opts


class ZhipuProvider(BaseProvider):
    name = "zhipu"
    label = "智谱 AI"
    vendor = "GLM-TTS · 音色复刻"
    description = "智谱 GLM-TTS-Clone 3 秒极速复刻，配合 GLM-TTS 合成，情感表达自然。"
    docs_url = "https://docs.bigmodel.cn/cn/guide/models/sound-and-video/glm-tts-clone"
    console_url = "https://bigmodel.cn/usercenter/proj-mgmt/apikeys"
    guide = [
        {
            "title": "注册智谱开放平台",
            "text": "注册并登录智谱开放平台，建议先完成实名认证。",
            "links": [{"label": "智谱开放平台", "url": "https://bigmodel.cn/"}],
        },
        {
            "title": "创建 API Key",
            "text": "在「项目管理 → API Keys」中添加新的 API Key 并填入下方。请使用「模型标准 API」的 Key，套餐类 Key 不能用于这里。",
            "links": [{"label": "API Keys", "url": "https://bigmodel.cn/usercenter/proj-mgmt/apikeys"}],
        },
        {
            "title": "了解计费",
            "text": "音色复刻按次计费，语音合成按字符计费，详见价格页。",
            "links": [
                {"label": "价格", "url": "https://bigmodel.cn/pricing"},
                {"label": "GLM-TTS-Clone 文档", "url": "https://docs.bigmodel.cn/cn/guide/models/sound-and-video/glm-tts-clone"},
            ],
        },
    ]
    color = "#2563eb"
    clone_audio_formats = ["mp3", "wav"]
    clone_tips = [
        "参考音频 3~30 秒，mp3/wav，≤10MB",
        "复刻时会使用「试听文本」生成一段示例音频",
        "填写参考音频对应的文本可提升复刻效果",
    ]
    capabilities = {"clone": True, "list": True, "delete": True, "query": True, "audio_url": False}
    models = [{"value": "glm-tts", "label": "GLM-TTS", "group": "GLM", "default": True}]
    credential_fields = [
        Field("api_key", "API Key", type="password", secret=True, required=True, env="ZHIPU_API_KEY",
              help="智谱开放平台 → API Keys"),
        Field("base_url", "API 地址", default="https://open.bigmodel.cn/api/paas/v4", env="ZHIPU_BASE_URL",
              placeholder="https://open.bigmodel.cn/api/paas/v4", group="advanced"),
    ]
    voice_id_field = Field("voice_id", "音色名称", placeholder="留空自动生成", help="平台内唯一的音色名称（voice_name）")
    clone_fields: list[Field] = []
    tts_params = [
        Field("speed", "语速", type="slider", default=1.0, min=0.5, max=2.0, step=0.05),
        Field("volume", "音量", type="slider", default=1.0, min=0.1, max=10, step=0.1),
        Field("format", "格式", type="select", default="wav", options=opts("wav")),
        Field("watermark_enabled", "AI 水印", type="switch", default=True, group="advanced",
              help="仅已在智谱控制台完成去水印申请的账号可关闭"),
    ]
    max_text_length = 1024

    @property
    def base(self) -> str:
        return self.cred("base_url", "https://open.bigmodel.cn/api/paas/v4").rstrip("/")

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.cred('api_key')}"}

    def _raise(self, resp, body: Any) -> None:
        err = (body or {}).get("error") if isinstance(body, dict) else None
        code = (err or {}).get("code") or resp.status_code
        msg = (err or {}).get("message") or resp.text[:300] or resp.reason_phrase
        raise ProviderError(f"智谱请求失败 [{code}]: {msg}", status_code=400 if resp.status_code < 500 else 502, raw=body)

    async def _request(self, method: str, path: str, **kw) -> dict:
        resp = await self.client.request(method, self.base + path, headers=self._auth(), **kw)
        body = self.parse_json(resp)
        if resp.status_code != 200 or (isinstance(body, dict) and body.get("error")):
            self._raise(resp, body)
        return body or {}

    # --------------------------------------------------------- operations
    async def test(self) -> str:
        await self._request("GET", "/voice/list", params={"voiceType": "PRIVATE"})
        return "连接成功"

    async def clone(self, req: CloneRequest) -> CloneResult:
        if not req.audio:
            raise ProviderError("请上传参考音频", status_code=400)
        mime = "audio/mpeg" if req.audio_format == "mp3" else "audio/wav"
        up = await self._request("POST", "/files", data={"purpose": "voice-clone-input"},
                                 files={"file": (f"reference.{req.audio_format}", req.audio, mime)})
        file_id = up.get("id")
        if not file_id:
            raise ProviderError("智谱文件上传未返回 id", raw=up)
        voice_name = (req.voice_id or "").strip() or self.slug(req.name, allowed=r"a-zA-Z0-9_\-", max_len=48)
        if not voice_name or not re.search(r"[A-Za-z]", voice_name):
            voice_name = self.gen_id("voxdock_")
        body: dict[str, Any] = {
            "model": "glm-tts-clone",
            "voice_name": voice_name,
            "input": req.demo_text or self.default_demo_text,
            "file_id": file_id,
            "request_id": str(uuid.uuid4()),
        }
        if req.transcript:
            body["text"] = req.transcript
        res = await self._request("POST", "/voice/clone", json=body)
        voice = res.get("voice")
        if not voice:
            raise ProviderError("智谱未返回音色 ID", raw=res)
        demo_audio, demo_fmt = None, ""
        if res.get("file_id"):
            try:
                r = await self.client.get(f"{self.base}/files/{res['file_id']}/content", headers=self._auth(), follow_redirects=True)
                if r.status_code == 200 and r.content and not r.headers.get("content-type", "").startswith("application/json"):
                    demo_audio = r.content
                    demo_fmt = "mp3" if "mpeg" in r.headers.get("content-type", "") else "wav"
            except Exception:  # noqa: BLE001 - demo audio is optional
                demo_audio = None
        return CloneResult(voice_id=voice, status="ready", model="glm-tts", demo_audio=demo_audio, demo_format=demo_fmt,
                           extra={"voice_name": voice_name, "demo_file_id": res.get("file_id")})

    async def list_voices(self) -> list[RemoteVoice]:
        res = await self._request("GET", "/voice/list", params={"voiceType": "PRIVATE"})
        return [
            RemoteVoice(
                voice_id=it.get("voice") or "",
                name=it.get("voice_name") or it.get("voice") or "",
                status="ready",
                model="glm-tts",
                demo_url=it.get("download_url") or "",
                created_at=it.get("create_time") or "",
                extra={"voice_name": it.get("voice_name"), "voice_type": it.get("voice_type")},
            )
            for it in res.get("voice_list") or []
        ]

    async def get_voice(self, voice_id: str, model: str = "", extra: dict | None = None) -> RemoteVoice | None:
        for v in await self.list_voices():
            if v.voice_id == voice_id:
                return v
        return None

    async def delete_voice(self, voice_id: str, model: str = "", extra: dict | None = None) -> None:
        await self._request("POST", "/voice/delete", json={"voice": voice_id, "request_id": str(uuid.uuid4())})

    async def synthesize(self, text: str, voice_id: str, model: str, params: dict[str, Any]) -> SynthesisResult:
        body: dict[str, Any] = {
            "model": "glm-tts",
            "input": text,
            "voice": voice_id,
            "response_format": "wav",
            "speed": round(self.num(params, "speed", 1.0, 0.5, 2.0), 2),
            "volume": round(self.num(params, "volume", 1.0, 0.1, 10), 2),
            "stream": False,
        }
        if params.get("watermark_enabled") is False:
            body["watermark_enabled"] = False
        resp = await self.client.post(self.base + "/audio/speech", json=body, headers=self._auth())
        ctype = resp.headers.get("content-type", "")
        if resp.status_code != 200 or ctype.startswith("application/json"):
            self._raise(resp, self.parse_json(resp))
        if not resp.content:
            raise ProviderError("智谱未返回音频数据")
        return SynthesisResult(audio=resp.content, format="wav", sample_rate=24000)
