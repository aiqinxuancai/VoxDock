"""MiniMax 快速复刻 + T2A v2."""
from __future__ import annotations

import re
from typing import Any

from .base import BaseProvider, CloneRequest, CloneResult, Field, ProviderError, RemoteVoice, SynthesisResult, opts

SPEECH_MODELS = [
    {"value": "speech-2.8-hd", "label": "Speech 2.8 HD", "group": "Speech 2.8", "default": True},
    {"value": "speech-2.8-turbo", "label": "Speech 2.8 Turbo", "group": "Speech 2.8"},
    {"value": "speech-2.6-hd", "label": "Speech 2.6 HD", "group": "Speech 2.6"},
    {"value": "speech-2.6-turbo", "label": "Speech 2.6 Turbo", "group": "Speech 2.6"},
    {"value": "speech-02-hd", "label": "Speech 02 HD", "group": "Speech 02"},
    {"value": "speech-02-turbo", "label": "Speech 02 Turbo", "group": "Speech 02"},
    {"value": "speech-01-hd", "label": "Speech 01 HD", "group": "Speech 01"},
    {"value": "speech-01-turbo", "label": "Speech 01 Turbo", "group": "Speech 01"},
]
LANGUAGE_BOOST = opts(
    ("", "不指定"), ("auto", "自动识别"), ("Chinese", "中文"), ("Chinese,Yue", "粤语"), ("English", "英语"),
    ("Japanese", "日语"), ("Korean", "韩语"), ("French", "法语"), ("German", "德语"), ("Spanish", "西班牙语"),
    ("Portuguese", "葡萄牙语"), ("Russian", "俄语"), ("Italian", "意大利语"), ("Arabic", "阿拉伯语"),
    ("Thai", "泰语"), ("Vietnamese", "越南语"), ("Indonesian", "印尼语"),
)
VOICE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{6,254}[A-Za-z0-9]$")


class MinimaxProvider(BaseProvider):
    name = "minimax"
    label = "MiniMax"
    vendor = "海螺 · 快速复刻"
    description = "MiniMax 快速复刻，10 秒音频即可复刻，音色可配合所有 Speech 模型使用。"
    docs_url = "https://platform.minimax.cn/docs/api-reference/voice-cloning-clone"
    console_url = "https://platform.minimax.cn/user-center/basic-information"
    guide = [
        {
            "title": "注册并完成实名认证",
            "text": "登录 MiniMax 开放平台，在「账户信息」中完成个人或企业认证，声音复刻功能必须认证后才能使用。",
            "links": [
                {"label": "登录平台", "url": "https://platform.minimax.cn/login"},
                {"label": "账户信息 / 认证", "url": "https://platform.minimax.cn/user-center/basic-information"},
            ],
        },
        {
            "title": "账户充值",
            "text": "在「余额」页面充值。余额为 0 时，即使配置正确也无法调用接口。",
            "links": [{"label": "余额充值", "url": "https://platform.minimax.cn/user-center/payment/balance"}],
        },
        {
            "title": "创建 API Key",
            "text": "在「接口密钥」中创建按量付费的 API Key 并填入下方。国际站用户需同时把 API 地址改为 https://api.minimax.io。",
            "links": [{"label": "接口密钥", "url": "https://platform.minimax.cn/user-center/basic-information/interface-key"}],
        },
        {
            "title": "注意音色有效期",
            "text": "复刻的音色如果 7 天内没有用于正式合成，会被平台自动删除，复刻后请尽快使用。",
            "links": [{"label": "快速复刻文档", "url": "https://platform.minimax.cn/docs/api-reference/voice-cloning-clone"}],
        },
    ]
    color = "#f23f5d"
    clone_audio_formats = ["mp3", "m4a", "wav"]
    clone_tips = [
        "参考音频 10 秒 ~ 5 分钟，≤20MB；需完成账号实名认证",
        "复刻音色需在 7 天内用于正式合成，否则会被平台自动删除",
        "复刻成功的音色首次合成后才会出现在平台音色列表中",
    ]
    capabilities = {"clone": True, "list": True, "delete": True, "query": True, "audio_url": False}
    models = SPEECH_MODELS
    credential_fields = [
        Field("api_key", "API Key", type="password", secret=True, required=True, env="MINIMAX_API_KEY",
              help="账户管理 → 接口密钥"),
        Field("base_url", "API 地址", default="https://api.minimax.cn", env="MINIMAX_BASE_URL",
              placeholder="https://api.minimax.cn", help="国际站: https://api.minimax.io"),
        Field("group_id", "Group ID", env="MINIMAX_GROUP_ID", group="advanced", help="可选，旧版接口需要"),
    ]
    voice_id_field = Field("voice_id", "自定义音色 ID", placeholder="留空自动生成",
                           help="8~256 位，字母开头，可含数字、- 和 _，不能以 -/_ 结尾，账号内唯一")
    clone_fields = [
        Field("need_noise_reduction", "降噪", type="switch", default=False),
        Field("need_volume_normalization", "音量归一化", type="switch", default=False),
        Field("language_boost", "语种增强", type="select", default="", options=LANGUAGE_BOOST),
        Field("validate_text", "用参考文本校验", type="switch", default=False, group="advanced",
              help="使用「参考文本」做 ASR 相似度校验，不一致时复刻失败"),
        Field("accuracy", "校验阈值", type="slider", default=0.7, min=0, max=1, step=0.05, group="advanced"),
    ]
    tts_params = [
        Field("model", "合成模型", type="select", default="", options=[{"value": "", "label": "音色默认"}] +
              [{"value": m["value"], "label": m["label"]} for m in SPEECH_MODELS]),
        Field("speed", "语速", type="slider", default=1.0, min=0.5, max=2.0, step=0.05),
        Field("volume", "音量", type="slider", default=1.0, min=0.1, max=10, step=0.1),
        Field("pitch", "音调", type="slider", default=0, min=-12, max=12, step=1, help="半音"),
        Field("emotion", "情绪", type="select", default="",
              options=opts(("", "自动"), ("happy", "高兴"), ("sad", "悲伤"), ("angry", "愤怒"), ("fearful", "害怕"),
                           ("disgusted", "厌恶"), ("surprised", "惊讶"), ("calm", "平静"), ("fluent", "生动"),
                           ("whisper", "低语"))),
        Field("format", "格式", type="select", default="mp3", options=opts("mp3", "wav", "flac")),
        Field("sample_rate", "采样率", type="select", default=32000, options=opts(8000, 16000, 22050, 24000, 32000, 44100)),
        Field("bitrate", "比特率", type="select", default=128000, group="advanced",
              options=opts((32000, "32k"), (64000, "64k"), (128000, "128k"), (256000, "256k"))),
        Field("language_boost", "语种增强", type="select", default="", options=LANGUAGE_BOOST, group="advanced"),
        Field("modify_pitch", "声音低沉/明亮", type="slider", default=0, min=-100, max=100, step=1, group="advanced"),
        Field("intensity", "声音力量感", type="slider", default=0, min=-100, max=100, step=1, group="advanced"),
        Field("timbre", "声音磁性/清脆", type="slider", default=0, min=-100, max=100, step=1, group="advanced"),
        Field("sound_effects", "音效", type="select", default="", group="advanced",
              options=opts(("", "无"), ("spacious_echo", "空旷回音"), ("auditorium_echo", "礼堂广播"),
                           ("lofi_telephone", "电话失真"), ("robotic", "机械音"))),
    ]
    max_text_length = 10000

    # ------------------------------------------------------------ helpers
    @property
    def base(self) -> str:
        return self.cred("base_url", "https://api.minimax.cn").rstrip("/")

    def _url(self, path: str) -> str:
        gid = self.cred("group_id")
        return f"{self.base}{path}" + (f"?GroupId={gid}" if gid else "")

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.cred('api_key')}"}

    async def _post(self, path: str, *, json: dict | None = None, files: Any = None, data: dict | None = None) -> dict:
        resp = await self.client.post(self._url(path), json=json, files=files, data=data, headers=self._auth())
        body = self.parse_json(resp) or {}
        base_resp = body.get("base_resp") or {}
        code = base_resp.get("status_code", 0 if resp.status_code == 200 else resp.status_code)
        if resp.status_code != 200 or code != 0:
            msg = base_resp.get("status_msg") or resp.text[:300] or resp.reason_phrase
            raise ProviderError(f"MiniMax 请求失败 [{code}]: {msg}", status_code=400 if resp.status_code < 500 else 502, raw=body)
        return body

    async def _upload(self, audio: bytes, fmt: str, purpose: str = "voice_clone") -> int:
        mime = {"mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4"}.get(fmt, "application/octet-stream")
        body = await self._post("/v1/files/upload", data={"purpose": purpose},
                                files={"file": (f"reference.{fmt}", audio, mime)})
        file_id = (body.get("file") or {}).get("file_id")
        if not file_id:
            raise ProviderError("MiniMax 文件上传未返回 file_id", raw=body)
        return int(file_id)

    async def _get_voices(self, voice_type: str = "all") -> dict:
        return await self._post("/v1/get_voice", json={"voice_type": voice_type})

    # --------------------------------------------------------- operations
    async def test(self) -> str:
        await self._get_voices("voice_cloning")
        return "连接成功"

    async def clone(self, req: CloneRequest) -> CloneResult:
        if not req.audio:
            raise ProviderError("请上传参考音频", status_code=400)
        voice_id = (req.voice_id or "").strip() or self.gen_id("VoxDock")
        if not VOICE_ID_RE.match(voice_id):
            raise ProviderError("音色 ID 需 8~256 位、字母开头，仅含字母数字 - _，且不能以 - 或 _ 结尾", status_code=400)
        o = req.options
        file_id = await self._upload(req.audio, req.audio_format)
        body: dict[str, Any] = {
            "file_id": file_id,
            "voice_id": voice_id,
            "need_noise_reduction": bool(o.get("need_noise_reduction")),
            "need_volume_normalization": bool(o.get("need_volume_normalization")),
        }
        model = req.model or self.default_model()
        if req.demo_text:
            body["text"] = req.demo_text[:1000]
            body["model"] = model
        if o.get("language_boost"):
            body["language_boost"] = o["language_boost"]
        if o.get("validate_text") and req.transcript:
            body["text_validation"] = req.transcript[:200]
            body["accuracy"] = float(o.get("accuracy") or 0.7)
        res = await self._post("/v1/voice_clone", json=body)
        sensitive = res.get("input_sensitive")
        if isinstance(sensitive, dict) and sensitive.get("type"):
            raise ProviderError(f"参考音频未通过内容审核 (type={sensitive.get('type')})", status_code=400, raw=res)
        return CloneResult(
            voice_id=voice_id,
            status="ready",
            model=model,
            demo_url=res.get("demo_audio") or "",
            message="复刻成功，请在 7 天内正式使用以保留音色",
            extra={"voice_type": "voice_cloning", "file_id": file_id},
        )

    def _parse_list(self, body: dict) -> list[RemoteVoice]:
        out = []
        for key in ("voice_cloning", "voice_generation"):
            for it in body.get(key) or []:
                desc = it.get("description") or []
                out.append(RemoteVoice(
                    voice_id=it.get("voice_id") or "",
                    name=it.get("voice_name") or it.get("voice_id") or "",
                    status="ready",
                    created_at=it.get("created_time") or "",
                    message="；".join(desc) if isinstance(desc, list) else str(desc),
                    extra={"voice_type": key},
                ))
        return out

    async def get_voice(self, voice_id: str, model: str = "", extra: dict | None = None) -> RemoteVoice | None:
        for v in self._parse_list(await self._get_voices("all")):
            if v.voice_id == voice_id:
                v.model = model
                return v
        return None  # cloned voices only appear after first real synthesis

    async def list_voices(self) -> list[RemoteVoice]:
        return self._parse_list(await self._get_voices("all"))

    async def delete_voice(self, voice_id: str, model: str = "", extra: dict | None = None) -> None:
        voice_type = (extra or {}).get("voice_type") or "voice_cloning"
        await self._post("/v1/delete_voice", json={"voice_type": voice_type, "voice_id": voice_id})

    async def synthesize(self, text: str, voice_id: str, model: str, params: dict[str, Any]) -> SynthesisResult:
        fmt = str(params.get("format") or "mp3")
        sample_rate = int(params.get("sample_rate") or 32000)
        bitrate = int(params.get("bitrate") or 128000)
        voice_setting: dict[str, Any] = {
            "voice_id": voice_id,
            "speed": round(self.num(params, "speed", 1.0, 0.5, 2.0), 2),
            "vol": round(self.num(params, "volume", 1.0, 0.1, 10), 2),
            "pitch": int(self.num(params, "pitch", 0, -12, 12)),
        }
        if params.get("emotion"):
            voice_setting["emotion"] = params["emotion"]
        body: dict[str, Any] = {
            "model": params.get("model") or model or self.default_model(),
            "text": text,
            "stream": False,
            "voice_setting": voice_setting,
            "audio_setting": {"sample_rate": sample_rate, "bitrate": bitrate, "format": fmt, "channel": 1},
            "output_format": "hex",
        }
        if params.get("language_boost"):
            body["language_boost"] = params["language_boost"]
        modify = {k: int(self.num(params, src, 0, -100, 100))
                  for k, src in (("pitch", "modify_pitch"), ("intensity", "intensity"), ("timbre", "timbre"))}
        modify = {k: v for k, v in modify.items() if v}
        if params.get("sound_effects"):
            modify["sound_effects"] = params["sound_effects"]
        if modify:
            body["voice_modify"] = modify
        res = await self._post("/v1/t2a_v2", json=body)
        hex_audio = (res.get("data") or {}).get("audio")
        if not hex_audio:
            raise ProviderError("MiniMax 未返回音频数据", raw=res)
        info = res.get("extra_info") or {}
        return SynthesisResult(
            audio=bytes.fromhex(hex_audio),
            format=fmt,
            sample_rate=info.get("audio_sample_rate") or sample_rate,
            duration_ms=info.get("audio_length"),
            extra={"usage_characters": info.get("usage_characters"), "trace_id": res.get("trace_id")},
        )
