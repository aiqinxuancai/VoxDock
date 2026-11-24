"""阿里云百炼 · CosyVoice / 千问 Qwen-Audio-TTS / 千问 Qwen3-TTS-VC 声音复刻."""
from __future__ import annotations

import base64
import secrets
from typing import Any

from .base import BaseProvider, CloneRequest, CloneResult, Field, ProviderError, RemoteVoice, SynthesisResult, opts

STATUS_MAP = {"OK": "ready", "DEPLOYING": "training", "UNDEPLOYED": "failed"}
ENROLL_PREFIXES = ["cosyvoice", "qwen-audio"]
QWEN_VC_PREFIXES = ["qwen3-tts", "qwen-tts"]
LANG_HINTS = opts(
    ("zh", "中文"), ("en", "英语"), ("ja", "日语"), ("ko", "韩语"), ("fr", "法语"), ("de", "德语"),
    ("ru", "俄语"), ("pt", "葡萄牙语"), ("es", "西班牙语"), ("it", "意大利语"), ("th", "泰语"),
    ("id", "印尼语"), ("vi", "越南语"), ("ms", "马来语"), ("fil", "菲律宾语"), ("ar", "阿拉伯语"),
)


def is_qwen_vc(model: str) -> bool:
    return any(model.startswith(p) for p in QWEN_VC_PREFIXES)


class AliyunProvider(BaseProvider):
    name = "aliyun"
    label = "阿里云百炼"
    vendor = "CosyVoice · 千问 Qwen-TTS"
    description = "通义 CosyVoice、千问 Qwen-Audio-TTS 与 Qwen3-TTS-VC 声音复刻，音色与目标模型绑定。"
    docs_url = "https://help.aliyun.com/zh/model-studio/voice-clone-design-http-api"
    console_url = "https://bailian.console.aliyun.com/"
    guide = [
        {
            "title": "开通阿里云百炼",
            "text": "使用阿里云账号登录百炼控制台并开通模型服务，新用户通常有免费额度。",
            "links": [{"label": "百炼控制台", "url": "https://bailian.console.aliyun.com/"}],
        },
        {
            "title": "创建 API Key",
            "text": "在「API Key」页面创建以 sk- 开头的密钥并填入下方。Key 只在创建时显示一次，请立即复制保存。",
            "links": [
                {"label": "API Key（华北2 北京）", "url": "https://bailian.console.aliyun.com/cn-beijing/model/settings/api-key"},
                {"label": "获取 API Key 文档", "url": "https://help.aliyun.com/zh/model-studio/get-api-key"},
            ],
        },
        {
            "title": "确认地域与 API 地址",
            "text": "北京地域使用默认地址。新加坡地域需使用国际站的 Key，并把 API 地址改为 https://dashscope-intl.aliyuncs.com。",
            "links": [{"label": "国际站控制台", "url": "https://modelstudio.console.alibabacloud.com/"}],
        },
        {
            "title": "选择复刻模型",
            "text": "复刻时选择 CosyVoice、千问 Qwen-Audio 或 Qwen3-TTS-VC，音色只能用于复刻时选择的模型。",
            "links": [
                {"label": "声音复刻文档", "url": "https://help.aliyun.com/zh/model-studio/voice-clone-design-http-api"},
                {"label": "模型与计费", "url": "https://help.aliyun.com/zh/model-studio/models"},
            ],
        },
    ]
    color = "#ff6a00"
    clone_audio_formats = ["wav", "mp3", "m4a"]
    clone_tips = [
        "音色与目标模型绑定，合成时只能使用复刻时选择的模型",
        "建议 10~20 秒清晰朗读音频，≤10MB；CosyVoice 复刻后需等待审核（通常数秒到数分钟）",
        "支持直接填写公网音频 URL，无需上传",
    ]
    capabilities = {"clone": True, "list": True, "delete": True, "query": True, "audio_url": True}
    models = [
        {"value": "cosyvoice-v3-plus", "label": "CosyVoice v3 Plus", "group": "CosyVoice", "default": True},
        {"value": "cosyvoice-v3-flash", "label": "CosyVoice v3 Flash", "group": "CosyVoice"},
        {"value": "cosyvoice-v3.5-plus", "label": "CosyVoice v3.5 Plus", "group": "CosyVoice"},
        {"value": "cosyvoice-v3.5-flash", "label": "CosyVoice v3.5 Flash", "group": "CosyVoice"},
        {"value": "qwen-audio-3.1-tts-plus", "label": "Qwen-Audio 3.1 TTS Plus", "group": "千问 Qwen-Audio"},
        {"value": "qwen-audio-3.1-tts-flash", "label": "Qwen-Audio 3.1 TTS Flash", "group": "千问 Qwen-Audio"},
        {"value": "qwen-audio-3.0-tts-plus", "label": "Qwen-Audio 3.0 TTS Plus", "group": "千问 Qwen-Audio"},
        {"value": "qwen-audio-3.0-tts-flash", "label": "Qwen-Audio 3.0 TTS Flash", "group": "千问 Qwen-Audio"},
        {"value": "qwen3-tts-vc-2026-01-22", "label": "Qwen3-TTS-VC (2026-01-22)", "group": "千问 Qwen3-TTS"},
    ]
    credential_fields = [
        Field("api_key", "API Key", type="password", secret=True, required=True, env="DASHSCOPE_API_KEY",
              placeholder="sk-xxxxxxxx", help="百炼控制台「API-KEY」页面创建；北京与新加坡地域的 Key 不通用"),
        Field("base_url", "API 地址", default="https://dashscope.aliyuncs.com", env="DASHSCOPE_BASE_URL",
              placeholder="https://dashscope.aliyuncs.com",
              help="新加坡: https://dashscope-intl.aliyuncs.com；也可用 https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com"),
        Field("workspace", "业务空间 ID", env="DASHSCOPE_WORKSPACE", group="advanced",
              help="可选，使用子业务空间时填写（X-DashScope-WorkSpace）"),
    ]
    voice_id_field = Field("voice_id", "音色前缀", placeholder="留空自动生成",
                           help="CosyVoice/Qwen-Audio: 字母数字 ≤10 位；Qwen3-TTS-VC: 字母数字下划线 ≤16 位")
    clone_fields = [
        Field("language", "音频语种", type="select", default="zh", options=LANG_HINTS, models=ENROLL_PREFIXES),
        Field("enable_preprocess", "音频预处理", type="switch", default=False, models=ENROLL_PREFIXES,
              help="降噪、增强与音量均衡，适合嘈杂录音（cosyvoice-v3-plus 不支持）"),
        Field("max_prompt_audio_length", "最大参考时长(秒)", type="number", min=3, max=30, step=1,
              group="advanced", models=ENROLL_PREFIXES),
    ]
    tts_params = [
        Field("speed", "语速", type="slider", default=1.0, min=0.5, max=2.0, step=0.05, models=ENROLL_PREFIXES),
        Field("volume", "音量", type="slider", default=50, min=0, max=100, step=1, models=ENROLL_PREFIXES),
        Field("pitch", "音调", type="slider", default=1.0, min=0.5, max=2.0, step=0.05, models=ENROLL_PREFIXES),
        Field("format", "格式", type="select", default="mp3", options=opts("mp3", "wav", ("opus", "opus")),
              models=ENROLL_PREFIXES),
        Field("sample_rate", "采样率", type="select", default=24000,
              options=opts(8000, 16000, 22050, 24000, 44100, 48000), models=ENROLL_PREFIXES),
        Field("instruction", "指令控制", type="textarea", models=ENROLL_PREFIXES,
              placeholder="例如：用开心、活泼的语气说话", help="控制情感/方言/角色，部分模型与音色支持，≤100 字符"),
        Field("language", "目标语种", type="select", default="", models=ENROLL_PREFIXES, group="advanced",
              options=[{"value": "", "label": "自动"}] + LANG_HINTS),
        Field("seed", "随机种子", type="number", min=0, max=65535, step=1, models=ENROLL_PREFIXES, group="advanced"),
        Field("language_type", "语种", type="select", default="Auto", models=QWEN_VC_PREFIXES,
              options=opts(("Auto", "自动"), ("Chinese", "中文"), ("English", "英语"), ("Japanese", "日语"),
                           ("Korean", "韩语"), ("German", "德语"), ("French", "法语"), ("Russian", "俄语"),
                           ("Italian", "意大利语"), ("Spanish", "西班牙语"), ("Portuguese", "葡萄牙语"))),
    ]
    max_text_length = 2000

    # ------------------------------------------------------------ helpers
    @property
    def base(self) -> str:
        return self.cred("base_url", "https://dashscope.aliyuncs.com").rstrip("/")

    def _headers(self) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self.cred('api_key')}", "Content-Type": "application/json"}
        if self.cred("workspace"):
            h["X-DashScope-WorkSpace"] = self.cred("workspace")
        return h

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        resp = await self.client.post(self.base + path, json=body, headers=self._headers())
        data = self.parse_json(resp) or {}
        if resp.status_code != 200 or (data.get("code") and not data.get("output")):
            msg = data.get("message") or resp.text[:300] or resp.reason_phrase
            code = data.get("code") or resp.status_code
            raise ProviderError(f"阿里云请求失败 [{code}]: {msg}", status_code=400 if resp.status_code < 500 else 502, raw=data)
        return data

    async def _enroll(self, input_: dict[str, Any], model: str = "voice-enrollment", parameters: dict | None = None):
        body: dict[str, Any] = {"model": model, "input": input_}
        if parameters:
            body["parameters"] = parameters
        return (await self._post("/api/v1/services/audio/tts/customization", body)).get("output") or {}

    @staticmethod
    def _prefix_of(voice_id: str, target_model: str) -> str:
        rest = voice_id[len(target_model) + 1:] if target_model and voice_id.startswith(target_model + "-") else voice_id
        return rest.split("-")[0] if rest else voice_id

    # --------------------------------------------------------- operations
    async def test(self) -> str:
        await self._enroll({"action": "list_voice", "page_size": 1, "page_index": 0})
        return "连接成功"

    async def clone(self, req: CloneRequest) -> CloneResult:
        model = req.model or self.default_model()
        if req.audio:
            audio = self.data_uri(req.audio, req.audio_format)
        elif req.audio_url:
            audio = req.audio_url
        else:
            raise ProviderError("请上传参考音频或填写音频 URL", status_code=400)
        o = req.options

        if is_qwen_vc(model):
            name = self.slug(req.voice_id or req.name, allowed=r"a-zA-Z0-9_", max_len=16) or f"vd_{secrets.token_hex(4)}"
            inp: dict[str, Any] = {"action": "create", "target_model": model, "preferred_name": name, "audio": {"data": audio}}
            if req.transcript:
                inp["text"] = req.transcript
            out = await self._enroll(inp, model="qwen-voice-enrollment")
            voice_id = out.get("voice")
            if not voice_id:
                raise ProviderError("阿里云未返回音色 ID", raw=out)
            return CloneResult(voice_id=voice_id, status="ready", model=out.get("target_model") or model,
                               extra={"family": "qwen-vc", "preferred_name": name})

        prefix = self.slug(req.voice_id or req.name, max_len=10, lower=True) or f"v{secrets.token_hex(4)}"
        inp = {"action": "create_voice", "target_model": model, "prefix": prefix, "audio": audio}
        if o.get("language"):
            inp["language_hints"] = [o["language"]]
        if o.get("enable_preprocess"):
            inp["enable_preprocess"] = True
        if o.get("max_prompt_audio_length"):
            inp["max_prompt_audio_length"] = float(o["max_prompt_audio_length"])
        try:
            out = await self._enroll(inp)
        except ProviderError as e:
            # older deployments only understand the legacy ``url`` field
            if not req.audio_url or "url" not in e.message.lower():
                raise
            inp.pop("audio")
            inp["url"] = req.audio_url
            out = await self._enroll(inp)
        voice_id = out.get("voice_id")
        if not voice_id:
            raise ProviderError("阿里云未返回音色 ID", raw=out)
        status, message = "training", "审核中"
        try:
            rv = await self.get_voice(voice_id, model)
            if rv:
                status, message = rv.status, rv.message
        except ProviderError:
            pass
        return CloneResult(voice_id=voice_id, status=status, model=model, message=message,
                           extra={"family": "enroll", "prefix": prefix})

    async def get_voice(self, voice_id: str, model: str = "", extra: dict | None = None) -> RemoteVoice | None:
        if is_qwen_vc(model) or (extra or {}).get("family") == "qwen-vc":
            for v in await self._list_qwen():
                if v.voice_id == voice_id:
                    return v
            return None
        out = await self._enroll({"action": "query_voice", "voice_id": voice_id})
        status = out.get("status") or ""
        target = out.get("target_model") or model
        return RemoteVoice(
            voice_id=voice_id,
            name=self._prefix_of(voice_id, target),
            status=STATUS_MAP.get(status, "unknown"),
            model=target,
            created_at=out.get("gmt_create") or "",
            message={"OK": "可用", "DEPLOYING": "审核中", "UNDEPLOYED": "审核未通过"}.get(status, status),
            extra={"family": "enroll", "resource_link": out.get("resource_link") or ""},
        )

    async def _list_enroll(self) -> list[RemoteVoice]:
        out: list[RemoteVoice] = []
        for page in range(20):
            res = await self._enroll({"action": "list_voice", "page_size": 100, "page_index": page})
            items = res.get("voice_list") or []
            for it in items:
                target = it.get("target_model") or ""
                vid = it.get("voice_id") or ""
                out.append(RemoteVoice(
                    voice_id=vid, name=self._prefix_of(vid, target), model=target,
                    status=STATUS_MAP.get(it.get("status") or "", "unknown"),
                    created_at=it.get("gmt_create") or "", extra={"family": "enroll"},
                ))
            if len(items) < 100:
                break
        return out

    async def _list_qwen(self) -> list[RemoteVoice]:
        out: list[RemoteVoice] = []
        for page in range(20):
            res = await self._enroll({"action": "list", "page_size": 100, "page_index": page}, model="qwen-voice-enrollment")
            items = res.get("voice_list") or []
            for it in items:
                target = it.get("target_model") or ""
                if target and not is_qwen_vc(target):
                    continue  # omni / livetranslate voices are not usable for TTS here
                out.append(RemoteVoice(voice_id=it.get("voice") or "", name=it.get("voice") or "", model=target,
                                       status="ready", created_at=it.get("gmt_create") or "", extra={"family": "qwen-vc"}))
            if len(items) < 100:
                break
        return out

    async def list_voices(self) -> list[RemoteVoice]:
        result, errors = [], []
        for fn in (self._list_enroll, self._list_qwen):
            try:
                result.extend(await fn())
            except ProviderError as e:
                errors.append(e)
        if errors and len(errors) == 2:
            raise errors[0]
        return result

    async def delete_voice(self, voice_id: str, model: str = "", extra: dict | None = None) -> None:
        if is_qwen_vc(model) or (extra or {}).get("family") == "qwen-vc":
            await self._enroll({"action": "delete", "voice": voice_id}, model="qwen-voice-enrollment")
        else:
            await self._enroll({"action": "delete_voice", "voice_id": voice_id})

    async def synthesize(self, text: str, voice_id: str, model: str, params: dict[str, Any]) -> SynthesisResult:
        model = model or self.default_model()
        if is_qwen_vc(model):
            inp: dict[str, Any] = {"text": text, "voice": voice_id}
            if params.get("language_type"):
                inp["language_type"] = params["language_type"]
            data = await self._post("/api/v1/services/aigc/multimodal-generation/generation", {"model": model, "input": inp})
            fmt, sample_rate = "wav", 24000
        else:
            fmt = str(params.get("format") or "mp3")
            sample_rate = int(params.get("sample_rate") or 24000)
            inp = {
                "text": text,
                "voice": voice_id,
                "format": fmt,
                "sample_rate": sample_rate,
                "volume": int(self.num(params, "volume", 50, 0, 100)),
                "rate": round(self.num(params, "speed", 1.0, 0.5, 2.0), 2),
                "pitch": round(self.num(params, "pitch", 1.0, 0.5, 2.0), 2),
            }
            if params.get("instruction"):
                inp["instruction"] = str(params["instruction"])[:100]
            if params.get("language"):
                inp["language_hints"] = [params["language"]]
            if params.get("seed") not in (None, ""):
                inp["seed"] = int(self.num(params, "seed", 0, 0, 65535))
            data = await self._post("/api/v1/services/audio/tts/SpeechSynthesizer", {"model": model, "input": inp})
        audio_obj = (data.get("output") or {}).get("audio") or {}
        if audio_obj.get("data"):
            audio = base64.b64decode(audio_obj["data"])
        elif audio_obj.get("url"):
            audio = await self.download(audio_obj["url"])
        else:
            raise ProviderError("阿里云未返回音频", raw=data)
        return SynthesisResult(audio=audio, format=fmt, sample_rate=sample_rate, extra={"usage": data.get("usage")})
