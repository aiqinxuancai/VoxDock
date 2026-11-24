---
name: voxdock-api
description: 调用 VoxDock 服务的 REST API：查询音色库、用克隆音色合成语音（TTS）、上传一段或多段参考音频复刻新音色、管理音色与合成历史，统一覆盖火山引擎、阿里云百炼（CosyVoice / 千问 Qwen-TTS）、MiniMax、智谱 GLM-TTS。当用户要生成语音或配音、克隆/复刻声音、查询或管理 VoxDock 音色、下载合成音频，或要在代码里接入 VoxDock（包括 OpenAI 兼容的 /v1/audio/speech）时使用。Use for VoxDock voice cloning and text-to-speech API calls.
---

# VoxDock API

VoxDock 是自托管的声音克隆聚合服务：把 4 个平台的「复刻音色」和「语音合成」封装成同一套 REST API。服务端负责保存平台密钥、音色库和合成历史，调用方只需要 VoxDock 的地址和 API Key。

## 1. 连接与鉴权

| 配置 | 环境变量 | 默认值 |
| --- | --- | --- |
| 服务地址 | `VOXDOCK_URL` | `http://localhost:8000` |
| API Key | `VOXDOCK_API_KEY` | 空（服务未设置管理员密码时不需要） |

API Key 以 `vd-` 开头，可在 Web「API 接入」页面创建。以下三种传法任选其一：
`Authorization: Bearer vd-xxx`、`X-API-Key: vd-xxx`、URL 参数 `?api_key=vd-xxx`（适合 `<audio src>`）。

**先确认连通性**（会检查服务、Key 是否有效、各平台是否已配置）：

```bash
python scripts/voxdock.py health
```

以下操作只能由管理员在 Web 界面完成，API Key 无权调用（返回 401/403）：填写平台密钥（`/api/providers/{name}/config`）、测试平台连接、管理 API Key。如果平台显示「未配置」，请让用户到 Web「平台配置」页面填写密钥，不要尝试用 API 绕过。

## 2. 首选：命令行客户端 `scripts/voxdock.py`

脚本只依赖 Python 标准库（3.8+），路径相对于本 skill 目录。完成一次性任务时优先用它，不用自己拼 HTTP 请求。

| 任务 | 命令 |
| --- | --- |
| 检查服务与配置 | `voxdock.py health` |
| 列出可用音色 | `voxdock.py voices --status ready`（`--provider minimax`、`-q 关键词`、`--json`） |
| 查看平台的模型 / 参数 / 复刻选项 | `voxdock.py providers aliyun` |
| 合成语音 | `voxdock.py tts <voice> "文本" -o out.mp3 --speed 1.1 --param emotion=happy` |
| 长文本 | `voxdock.py tts <voice> --text-file script.txt -o out.mp3`（或通过标准输入 `-`） |
| 复刻（可多段） | `voxdock.py clone --provider minimax --name 我的声音 a.wav b.wav --transcript "…" --wait` |
| 等待训练完成 | `voxdock.py wait <id>`（失败时退出码为 2） |
| 加入已有平台音色 | `voxdock.py add minimax male-qn-qingse --name 青涩青年` |
| 编辑音色 / 默认参数 | `voxdock.py update <id> --favorite true --default-param speed=1.1` |
| 从平台同步音色 | `voxdock.py sync aliyun` |
| 合成历史 / 下载 | `voxdock.py history --limit 10`，`voxdock.py download <generation_id> -o a.mp3` |
| 删除音色 | `voxdock.py delete <id>`（加 `--remote` 会同时删除平台上的音色，不可恢复） |

`tts` 成功后输出一行 JSON：`file`、`format`、`duration_ms`、`generation_id`、`provider`、`voice_id`。如果平台实际返回的格式与 `-o` 的扩展名不同，脚本会自动改正扩展名，实际路径以 `file` 为准。

## 3. 指定音色（`voice` 参数）

`voice` 按以下顺序解析：
1. 纯数字：音色库 ID，例如 `12`
2. `provider:voice_id`：平台前缀加平台音色 ID，例如 `minimax:male-qn-qingse`、`zhipu:tongtong`。音色不在音色库里也能直接合成，适合平台系统音色
3. 平台音色 ID，例如 `S_abc123`
4. 音色名称（完全匹配），例如 `温柔知性女声`

不确定用哪个音色时，先运行 `voices --status ready` 列出来，再让用户选择或按名称、标签匹配。`training` 状态的音色还在训练或审核中，`failed` 状态的音色不能用于合成。

## 4. 合成语音

```bash
curl -X POST "$VOXDOCK_URL/api/tts" -H "Authorization: Bearer $VOXDOCK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"voice": 12, "text": "你好，欢迎使用 VoxDock", "speed": 1.1, "format": "mp3"}' -o out.mp3
```

- `output`：`audio`（默认，直接返回音频，响应头带 `X-Generation-Id`、`X-Audio-Duration-Ms`）、`url`（返回 JSON，音频地址在 `audio_url` 字段）、`base64`（音频以 base64 放在 JSON 的 `audio_base64` 字段）。
- 快捷字段 `format / speed / volume / pitch / sample_rate / emotion / instruction / language` 会合并进 `params`，`params` 里的同名键优先。其他平台专属参数（如 MiniMax 的 `bitrate`、`timbre`，阿里的 `seed`，火山的 `tts_model`）放进 `params`。
- **各平台参数的取值范围不同**：音量在阿里是 0~100，在其他平台是倍数；音调在火山和 MiniMax 是 -12~12 个半音，在阿里是 0.5~2 的倍数，智谱没有音调参数。不确定时先运行 `providers <name>`，或查阅 [reference/providers.md](reference/providers.md)。
- 参数合并顺序：平台默认值 → 音色的 `default_params` → 本次请求。请求的格式平台不支持时，会回退到平台默认格式（例如智谱只输出 wav），实际格式以响应的 `Content-Type` 为准。
- 文本长度上限：火山 5000、阿里 2000、MiniMax 10000、智谱 1024 字符。超长文本需要按句子拆分后多次合成。
- 设置 `"save": false` 时不写入合成历史。

## 5. 复刻音色

```bash
curl -X POST "$VOXDOCK_URL/api/voices/clone" -H "Authorization: Bearer $VOXDOCK_API_KEY" \
  -F provider=aliyun -F name=我的声音 -F model=cosyvoice-v3-plus \
  -F transcript="第一段的文本。第二段的文本。" \
  -F file=@part1.wav -F file=@part2.mp3
```

- **多段参考音频**：`file` 字段可以重复传。4 个平台目前都只接收一条参考音频，服务端会按上传顺序合并成一条 24kHz WAV，每段之间插入 2 秒静音。`transcript` 要按同样顺序写出全部片段的内容。返回结果的 `extra.reference_count`、`extra.merged`、`extra.reference_duration_ms` 记录了合并信息。
- 合并后的总时长要符合平台限制（智谱 3~30 秒，火山建议 10~30 秒，阿里建议 10~20 秒，MiniMax 10 秒~5 分钟）。服务端没有 ffmpeg 时，多段合并只支持 WAV。
- 各平台的要求：
  - 火山：`voice_id` 必填，需要先在控制台购买音色，获得 `S_` 开头的 ID
  - 阿里：音色与 `model` 绑定，合成时只能用复刻时选择的模型；可以用 `audio_url` 代替上传文件
  - MiniMax：复刻的音色 7 天内没有用于合成会被平台删除
  - 智谱：`demo_text` 会用来生成一段试听音频
- 平台专属选项以 JSON 格式放在 `options` 表单字段（CLI 用 `--option k=v`），可选项见 `providers <name>` 的输出。
- **状态**：火山和阿里 CosyVoice 复刻后通常先返回 `training`，服务端会在后台自动轮询。也可以用 `POST /api/voices/{id}/refresh` 主动查询，或运行 `voxdock.py wait <id>` 等待。MiniMax 和智谱一般直接返回 `ready`。
- 复刻会占用平台额度并可能产生费用，请先和用户确认平台、名称和参考音频。只复刻用户本人或已获授权的声音。

## 6. 在代码中集成

```python
import requests
BASE, H = "http://localhost:8000", {"Authorization": "Bearer vd-xxx"}

voices = requests.get(f"{BASE}/api/voices", params={"status": "ready"}, headers=H).json()["items"]
r = requests.post(f"{BASE}/api/tts", headers=H, json={"voice": voices[0]["id"], "text": "你好", "params": {"speed": 1.1}})
r.raise_for_status()
open("out." + r.headers["content-type"].split("/")[-1].replace("mpeg", "mp3"), "wb").write(r.content)
```

使用 OpenAI SDK 时，把 `base_url` 设为 `{VOXDOCK_URL}/v1`，`api_key` 设为 VoxDock 的 Key。`voice` 的写法与第 3 节相同；`model` 字段会被忽略，填平台名（如 `minimax`）时强制使用该平台。

```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8000/v1", api_key="vd-xxx")
client.audio.speech.with_streaming_response.create(model="tts-1", voice="12", input="你好").stream_to_file("out.mp3")
```

全部接口、字段和响应结构见 [reference/endpoints.md](reference/endpoints.md)。服务本身也提供交互式文档：`{VOXDOCK_URL}/docs`。

## 7. 错误处理

错误响应统一为 `{"detail": "中文说明"}`，平台返回的错误信息会原样带出：

| 状态码 | 常见原因 | 处理 |
| --- | --- | --- |
| 400 | 平台未配置密钥、文本过长、参数或音频不合法、音色复刻失败 | 按 `detail` 修正；未配置时请用户去 Web 填写密钥 |
| 401 / 403 | 缺少 API Key 或 Key 无效 / 调用了仅限管理员的接口 | 设置 `VOXDOCK_API_KEY` |
| 404 | 音色或历史记录不存在 | 运行 `voices` 确认 ID 或名称 |
| 409 | 添加的平台音色已在音色库中 | 直接使用已有记录 |
| 502 / 504 | 连接平台失败或超时 | 稍后重试，长文本可以拆分 |
