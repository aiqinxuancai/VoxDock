"""火山引擎 · 豆包语音 声音复刻 (V3 API)."""
from __future__ import annotations

import base64
import json
import re
import uuid
from typing import Any

from ..audio import pcm_to_wav
from .base import BaseProvider, CloneRequest, CloneResult, Field, ProviderError, RemoteVoice, SynthesisResult, opts

STATUS_MAP = {0: "unknown", 1: "training", 2: "ready", 3: "failed", 4: "ready"}
STATUS_TEXT = {0: "未找到训练记录", 1: "训练中", 2: "训练完成", 3: "训练失败", 4: "已激活"}
LANGS = opts(
    ("0", "中文"), ("1", "英语"), ("2", "日语"), ("3", "西班牙语"), ("4", "印尼语"),
    ("5", "葡萄牙语"), ("6", "德语"), ("7", "法语"), ("8", "韩语"),
)


class VolcengineProvider(BaseProvider):
    name = "volcengine"
    label = "火山引擎"
    vendor = "豆包语音 · 声音复刻"
    description = "字节跳动豆包语音声音复刻 1.0 / 2.0，需先在控制台购买音色槽位 (S_xxx)。"
    docs_url = "https://www.volcengine.com/docs/6561/2227958"
    console_url = "https://console.volcengine.com/speech/new/overview?projectName=default"
    guide = [
        {
            "title": "开通声音复刻服务",
            "text": "登录火山引擎豆包语音控制台，在「开通管理」中开通「豆包声音复刻模型 2.0」（或 1.0）。",
            "links": [
                {"label": "开通管理", "url": "https://console.volcengine.com/speech/new/setting/activate?ResourceID=volc.seedicl.default&projectName=default"},
                {"label": "控制台指引", "url": "https://docs.volcengine.com/docs/doubao-voice/console-guidance?lang=zh"},
            ],
        },
        {
            "title": "购买音色槽位，获取音色 ID",
            "text": "预付费需下单购买音色槽位，后付费需开通后付费音色服务。在「音色库」中复制 S_ 开头的音色 ID。",
            "links": [
                {"label": "购买页面", "url": "https://console.volcengine.com/speech/new/purchase?projectName=default"},
                {"label": "音色库", "url": "https://console.volcengine.com/speech/new/voices?ResourceID=volc.seedicl.default&projectName=default"},
                {"label": "下单及使用指南", "url": "https://www.volcengine.com/docs/6561/1167802"},
            ],
        },
        {
            "title": "创建 API Key",
            "text": "在「API Key 管理」中创建 Key 并填入下方。旧版控制台用户可以改填 App ID 和 Access Token。",
            "links": [
                {"label": "API Key 管理", "url": "https://console.volcengine.com/speech/new/setting/apikeys?projectName=default"},
                {"label": "旧版应用管理", "url": "https://console.volcengine.com/speech/app"},
            ],
        },
        {
            "title": "填写已购音色 ID",
            "text": "把音色 ID 填入「已购音色 ID」后保存。之后复刻时填写该 ID，或点击「同步音色」导入已训练的音色。",
            "links": [{"label": "声音复刻 API 文档", "url": "https://www.volcengine.com/docs/6561/2227958"}],
        },
    ]
    color = "#3370ff"
    clone_audio_formats = ["wav", "mp3", "ogg", "m4a", "aac"]
    clone_tips = [
        "需先在火山控制台「声音复刻」购买音色，获得 S_ 开头的音色 ID",
        "建议 10~30 秒清晰人声，无背景音乐，≤10MB",
        "每个音色 ID 有训练次数上限，可重复上传覆盖",
    ]
    capabilities = {"clone": True, "list": True, "delete": False, "query": True, "audio_url": False}
    models = [
        {"value": "seed-icl-2.0", "label": "声音复刻 2.0", "group": "seed-icl", "default": True},
        {"value": "seed-icl-1.0", "label": "声音复刻 1.0", "group": "seed-icl"},
        {"value": "seed-icl-1.0-concurr", "label": "声音复刻 1.0 并发版", "group": "seed-icl"},
    ]
    credential_fields = [
        Field("api_key", "API Key", type="password", secret=True, env="VOLC_API_KEY",
              help="新版控制台「API Key 管理」中创建，与 AppID+Token 二选一", placeholder="新版控制台 API Key"),
        Field("app_id", "App ID", env="VOLC_APP_ID", help="旧版控制台应用 AppID"),
        Field("access_token", "Access Token", type="password", secret=True, env="VOLC_ACCESS_TOKEN",
              help="旧版控制台应用 Access Token"),
        Field("speaker_ids", "已购音色 ID", type="textarea", env="VOLC_SPEAKER_IDS",
              placeholder="S_xxxxxxx1, S_xxxxxxx2",
              help="火山没有音色列表接口，填写后「同步」时逐个查询状态（逗号或换行分隔）"),
        Field("base_url", "API 地址", default="https://openspeech.bytedance.com", env="VOLC_BASE_URL",
              placeholder="https://openspeech.bytedance.com", group="advanced"),
    ]
    voice_id_field = Field("voice_id", "音色 ID", required=True, placeholder="S_xxxxxxxx",
                           help="控制台购买的音色 ID；后付费可开启「自定义 ID」并填写任意合法 ID")
    clone_fields = [
        Field("language", "音频语种", type="select", default="0", options=LANGS),
        Field("enable_audio_denoise", "降噪", type="switch", default=False, help="会一定程度影响音色细节"),
        Field("voice_clone_enable_mss", "背景音分离", type="switch", default=False, help="去除背景音乐/噪声"),
        Field("custom_id", "自定义 ID（后付费）", type="switch", default=False, group="advanced",
              help="开启后音色 ID 作为 custom_speaker_id 提交"),
        Field("disable_volume_normalization", "关闭音量均衡", type="switch", default=False, group="advanced"),
        Field("enable_crop_by_asr", "ASR 智能裁剪", type="switch", default=False, group="advanced"),
    ]
    tts_params = [
        Field("speed", "语速", type="slider", default=1.0, min=0.5, max=2.0, step=0.05),
        Field("volume", "音量", type="slider", default=1.0, min=0.5, max=2.0, step=0.05),
        Field("pitch", "音调", type="slider", default=0, min=-12, max=12, step=1, help="半音"),
        Field("format", "格式", type="select", default="mp3", options=opts("mp3", "wav", ("ogg_opus", "ogg")),),
        Field("sample_rate", "采样率", type="select", default=24000,
              options=opts(8000, 16000, 22050, 24000, 32000, 44100, 48000)),
        Field("tts_model", "合成模型", type="select", default="", models=["seed-icl-2.0"],
              options=opts(("", "默认"), ("seed-tts-2.0-standard", "2.0 标准"), ("seed-tts-2.0-expressive", "2.0 表现力增强"))),
        Field("language", "朗读语种", type="select", default="", group="advanced",
              options=opts(("", "自动"), ("zh-cn", "中文"), ("en", "英语"), ("ja", "日语"), ("ko", "韩语"),
                           ("es-mx", "西班牙语"), ("id", "印尼语"), ("pt-br", "葡萄牙语"), ("de", "德语"), ("fr", "法语"))),
        Field("silence_duration", "句尾静音(ms)", type="number", min=0, max=30000, step=100, group="advanced"),
    ]

    @classmethod
    def required_credentials(cls) -> list[list[str]]:
        return [["api_key"], ["app_id", "access_token"]]

    # ------------------------------------------------------------ helpers
    @property
    def base(self) -> str:
        return self.cred("base_url", "https://openspeech.bytedance.com").rstrip("/")

    def _headers(self, resource_id: str | None = None) -> dict[str, str]:
        h = {"Content-Type": "application/json", "X-Api-Request-Id": str(uuid.uuid4())}
        if self.cred("api_key"):
            h["X-Api-Key"] = self.cred("api_key")
        else:
            app_id = self.cred("app_id")
            h["X-Api-App-Id"] = app_id  # synthesis
            h["X-Api-App-Key"] = app_id  # clone/status
            h["X-Api-Access-Key"] = self.cred("access_token")
        if resource_id:
            h["X-Api-Resource-Id"] = resource_id
        return h

    @staticmethod
    def _err(data: Any) -> tuple[Any, str]:
        """Errors come as {code, message} or {header: {code, message}}."""
        if not isinstance(data, dict):
            return None, ""
        src = data.get("header") if isinstance(data.get("header"), dict) else data
        return src.get("code"), src.get("message") or ""

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        resp = await self.client.post(self.base + path, json=body, headers=self._headers())
        data = self.parse_json(resp)
        if resp.status_code != 200:
            code, msg = self._err(data)
            raise ProviderError(f"火山引擎请求失败 [{code or resp.status_code}]: {msg or resp.text[:300] or resp.reason_phrase}",
                                status_code=400 if resp.status_code < 500 else 502, raw=data)
        return data or {}

    @staticmethod
    def _speaker_body(voice_id: str, extra: dict | None) -> dict[str, Any]:
        if (extra or {}).get("custom_id"):
            return {"speaker_id": "custom_speaker_id", "custom_speaker_id": voice_id}
        return {"speaker_id": voice_id}

    @staticmethod
    def _parse_voice(data: dict[str, Any], voice_id: str) -> RemoteVoice:
        status = int(data.get("status") or 0)
        demo, model_type = "", 0
        for item in data.get("speaker_status") or []:
            mt = int(item.get("model_type") or 0)
            if item.get("demo_audio") and mt >= model_type:
                demo, model_type = item["demo_audio"], mt
        model = "seed-icl-2.0" if model_type >= 4 else ("seed-icl-1.0" if model_type else "")
        return RemoteVoice(
            voice_id=voice_id,
            name=voice_id,
            status=STATUS_MAP.get(status, "unknown"),
            model=model,
            demo_url=demo,
            created_at=str(data.get("create_time") or ""),
            message=STATUS_TEXT.get(status, ""),
            extra={"available_training_times": data.get("available_training_times"), "raw_status": status},
        )

    # --------------------------------------------------------- operations
    async def test(self) -> str:
        try:
            await self._post("/api/v3/tts/get_voice", {"speaker_id": "S_voxdock_probe"})
        except ProviderError as e:
            if re.search(r"auth|401|403|forbidden|unauthori|invalid.*(key|token)|鉴权", e.message, re.I):
                raise
        return "鉴权通过"

    async def clone(self, req: CloneRequest) -> CloneResult:
        voice_id = req.voice_id.strip()
        if not voice_id:
            raise ProviderError("火山引擎需要填写控制台购买的音色 ID（S_xxx）", status_code=400)
        if not req.audio:
            raise ProviderError("请上传参考音频", status_code=400)
        o = req.options
        custom = bool(o.get("custom_id"))
        body: dict[str, Any] = self._speaker_body(voice_id, {"custom_id": custom})
        body["audio"] = {"data": self.b64(req.audio), "format": req.audio_format}
        if req.transcript:
            body["text"] = req.transcript
        try:
            body["language"] = int(o.get("language", 0) or 0)
        except (TypeError, ValueError):
            body["language"] = 0
        extra_params: dict[str, Any] = {}
        if req.demo_text:
            extra_params["demo_text"] = req.demo_text[:300]
        for key in ("enable_audio_denoise", "voice_clone_enable_mss", "disable_volume_normalization", "enable_crop_by_asr"):
            if key in o:
                extra_params[key] = bool(o[key])
        if extra_params:
            body["extra_params"] = extra_params
        data = await self._post("/api/v3/tts/voice_clone", body)
        rv = self._parse_voice(data, voice_id)
        status = rv.status if rv.status != "unknown" else "training"
        return CloneResult(
            voice_id=voice_id,
            status=status,
            model=rv.model or req.model or self.default_model(),
            demo_url=rv.demo_url,
            message=rv.message,
            extra={"custom_id": custom, **rv.extra},
        )

    async def get_voice(self, voice_id: str, model: str = "", extra: dict | None = None) -> RemoteVoice | None:
        data = await self._post("/api/v3/tts/get_voice", self._speaker_body(voice_id, extra))
        rv = self._parse_voice(data, voice_id)
        if not rv.model:
            rv.model = model
        return rv

    async def list_voices(self) -> list[RemoteVoice]:
        ids = [s for s in re.split(r"[\s,，;；]+", self.cred("speaker_ids")) if s]
        out = []
        for sid in dict.fromkeys(ids):
            try:
                rv = await self.get_voice(sid)
            except ProviderError as e:
                out.append(RemoteVoice(voice_id=sid, name=sid, status="unknown", message=e.message))
                continue
            if rv and rv.extra.get("raw_status") != 0:
                out.append(rv)
        return out

    async def synthesize(self, text: str, voice_id: str, model: str, params: dict[str, Any]) -> SynthesisResult:
        resource_id = model or self.default_model()
        fmt = str(params.get("format") or "mp3")
        wire_fmt = "pcm" if fmt == "wav" else fmt
        sample_rate = int(params.get("sample_rate") or 24000)
        audio_params: dict[str, Any] = {
            "format": wire_fmt,
            "sample_rate": sample_rate,
            "speech_rate": int(round((self.num(params, "speed", 1.0, 0.5, 2.0) - 1) * 100)),
            "loudness_rate": int(round((self.num(params, "volume", 1.0, 0.5, 2.0) - 1) * 100)),
        }
        req_params: dict[str, Any] = {"text": text, "speaker": voice_id, "audio_params": audio_params}
        if params.get("tts_model") and resource_id == "seed-icl-2.0":
            req_params["model"] = params["tts_model"]
        additions: dict[str, Any] = {}
        pitch = int(self.num(params, "pitch", 0, -12, 12))
        if pitch:
            additions["post_process"] = {"pitch": pitch}
        if params.get("language"):
            additions["explicit_language"] = params["language"]
        if params.get("silence_duration"):
            additions["silence_duration"] = int(self.num(params, "silence_duration", 0, 0, 30000))
        if additions:
            req_params["additions"] = json.dumps(additions, ensure_ascii=False)
        body = {"user": {"uid": "voxdock"}, "req_params": req_params}

        resp = await self.client.post(self.base + "/api/v3/tts/unidirectional", json=body,
                                      headers=self._headers(resource_id))
        raw = resp.text
        if resp.status_code != 200:
            data = self.parse_json(resp) or {}
            code, msg = self._err(data)
            raise ProviderError(f"火山引擎合成失败 [{code or resp.status_code}]: {msg or raw[:300]}",
                                status_code=400 if resp.status_code < 500 else 502, raw=data)
        chunks: list[bytes] = []
        usage = None
        decoder, pos = json.JSONDecoder(), 0
        while pos < len(raw):
            while pos < len(raw) and raw[pos] in " \r\n\t":
                pos += 1
            if pos >= len(raw):
                break
            try:
                obj, pos = decoder.raw_decode(raw, pos)
            except json.JSONDecodeError:
                break
            if not isinstance(obj, dict):
                continue
            code, msg = self._err(obj)
            if isinstance(obj.get("data"), str) and obj["data"]:
                chunks.append(base64.b64decode(obj["data"]))
            elif code not in (0, 20000000, None):
                raise ProviderError(f"火山引擎合成失败 [{code}]: {msg}", raw=obj)
            usage = obj.get("usage") or usage
        audio = b"".join(chunks)
        if not audio:
            raise ProviderError("火山引擎未返回音频数据，请检查音色 ID 与模型版本（Resource-Id）是否匹配")
        if fmt == "wav":
            audio = pcm_to_wav(audio, sample_rate)
        return SynthesisResult(audio=audio, format=fmt, sample_rate=sample_rate, extra={"usage": usage} if usage else {})
