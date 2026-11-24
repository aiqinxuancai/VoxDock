# VoxDock 接口参考

所有路径都相对于服务地址（默认 `http://localhost:8000`）。标记 🔓 的接口不需要鉴权；标记 🛡 的接口只能由管理员在 Web 登录后调用，API Key 无权访问；其余接口需要 API Key（服务未设置管理员密码时都不需要鉴权）。

错误响应统一为 `{"detail": "说明"}`。

## 目录

- [系统与鉴权](#系统与鉴权)
- [平台](#平台)
- [音色](#音色)
- [合成](#合成)
- [合成历史](#合成历史)
- [OpenAI 兼容](#openai-兼容)
- [数据结构](#数据结构)

## 系统与鉴权

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/healthz` | 🔓 健康检查，返回 `{"status": "ok", "version": "1.0.0"}` |
| `GET` | `/api/auth/status` | 🔓 返回 `auth_enabled`、`authenticated`、`identity`（`open` / `session` / `api_key` / `null`）；可用来验证 API Key 是否有效 |
| `POST` | `/api/auth/login` | 🔓 Web 管理员登录，请求体 `{"password": "..."}`，成功后写入会话 Cookie |
| `POST` | `/api/auth/logout` | 退出登录 |
| `GET` | `/api/system` | 版本、`ffmpeg` 是否可用、`max_reference_audios`、`merge_gap_seconds`、`max_upload_mb`，以及统计信息 `stats` |
| `GET` | `/api/keys` | 🛡 API Key 列表 |
| `POST` | `/api/keys` | 🛡 创建 API Key，请求体 `{"name": "my-app"}`；明文 `key` 只在这次响应里返回 |
| `DELETE` | `/api/keys/{key_id}` | 🛡 删除 API Key |

## 平台

平台名固定为：`volcengine`（火山引擎）、`aliyun`（阿里云百炼）、`minimax`、`zhipu`（智谱 AI）。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/providers` | 平台列表 `{"items": [Provider]}` |
| `GET` | `/api/providers/{name}` | 单个平台的 Provider 对象 |
| `GET` | `/api/providers/{name}/config` | 🛡 读取平台密钥（脱敏）与来源 |
| `PUT` | `/api/providers/{name}/config` | 🛡 更新平台密钥，请求体 `{"values": {...}, "enabled": true}` |
| `POST` | `/api/providers/{name}/test` | 🛡 测试平台连接 |
| `POST` | `/api/providers/{name}/sync` | 从平台拉取音色列表写入音色库，返回 `{"added", "updated", "total"}` |

**Provider 对象**中常用的字段：

- `configured` / `enabled`：是否已配置密钥、是否启用
- `models`（`[{value, label}]`）、`default_model`、`max_text_length`
- `tts_params`：合成参数定义，每项包含 `key`、`type`（slider / select / number / switch / textarea）、`default`、`min`、`max`、`options`、`models`（只对这些模型前缀生效）、`group`（basic / advanced）
- `clone_fields`：复刻选项定义（结构同上），通过复刻接口的 `options` 字段提交
- `voice_id_field`：复刻时 `voice_id` 的含义与是否必填（火山为必填）
- `capabilities`：`clone`、`list`、`delete`、`query`、`audio_url`（复刻时能否使用 URL）
- `max_reference_audios`：平台原生支持的参考音频条数（目前都是 1，超出时服务端合并）
- `clone_audio_formats`、`clone_tips`、`guide`（接入步骤）、`docs_url`、`console_url`

## 音色

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/voices` | 音色列表 `{"items": [Voice]}`。查询参数：`provider`、`status`（ready / training / failed / unknown）、`q`（匹配名称、音色 ID、描述）、`favorite`（true / false）。按收藏优先、最近更新排序 |
| `POST` | `/api/voices` | 把已有的平台音色或系统音色加入音色库（JSON，见下文），已存在时返回 409 |
| `POST` | `/api/voices/clone` | 上传参考音频复刻新音色（multipart，见下文），返回 Voice |
| `GET` | `/api/voices/{id}` | 音色详情 |
| `PATCH` | `/api/voices/{id}` | 编辑音色，字段均可选：`name`、`description`、`tags`（数组，整体替换）、`favorite`、`model`、`default_params`（对象，整体替换） |
| `DELETE` | `/api/voices/{id}` | 删除音色。`?remote=true` 时同时删除平台上的音色（不可恢复）；`?force=true` 时平台删除失败也删除本地记录 |
| `POST` | `/api/voices/{id}/refresh` | 向平台查询一次训练状态，返回更新后的 Voice |
| `GET` | `/api/voices/{id}/sample` | 参考音频（多段时为合并后的音频） |
| `GET` | `/api/voices/{id}/demo` | 平台生成的试听音频 |

### 添加已有音色 `POST /api/voices`

```json
{"provider": "minimax", "voice_id": "male-qn-qingse", "name": "青涩青年", "model": "", "description": "", "tags": [], "default_params": {"speed": 1.1}}
```

`provider` 和 `voice_id` 必填。只想临时使用平台系统音色时，不需要加入音色库，合成时直接写 `"voice": "minimax:male-qn-qingse"` 即可。

### 复刻 `POST /api/voices/clone`（multipart/form-data）

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `provider` | ✅ | `volcengine` / `aliyun` / `minimax` / `zhipu` |
| `name` | ✅ | 在音色库里显示的名称 |
| `file` | ✅* | 参考音频文件，可以重复传多个。平台只支持单条时，按顺序合并成 24kHz WAV，每段间隔 2 秒。最多 10 段，单个文件 ≤20MB（服务端可配置） |
| `audio_url` | ✅* | 公网音频 URL，可代替 `file`（仅阿里云支持） |
| `model` | | 目标模型，留空时使用平台默认模型 |
| `voice_id` | | 平台音色 ID 或前缀，留空时自动生成；**火山必填**（`S_` 开头） |
| `transcript` | | 参考音频对应的文本；多段时按顺序写出全部内容 |
| `demo_text` | | 试听文本，部分平台复刻后会用它生成试听音频 |
| `description` | | 描述 |
| `tags` | | 标签，用逗号分隔 |
| `options` | | 平台专属选项，JSON 对象字符串，可选项见 Provider 的 `clone_fields` |

\* `file` 和 `audio_url` 至少提供一个。

返回的 Voice 里，`status` 为 `training` 时表示平台还在训练或审核，服务端会在后台每 6 秒轮询一次（最多约 5 分钟）。`extra` 中包含：
- `reference_count`：参考音频段数
- `merged`：是否在本地合并过
- `merge_gap_seconds`：合并时的静音间隔
- `reference_duration_ms`：合并后的总时长
- `options`：本次提交的平台选项

## 合成

### `POST /api/tts`（JSON）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `voice` | string / int | **必填**。音色库 ID、`provider:voice_id`、平台音色 ID 或音色名称 |
| `text` | string | **必填**。合成文本，长度上限见各平台说明 |
| `provider` | string | `voice` 为平台原始 ID 时可用它指定平台 |
| `model` | string | 覆盖音色绑定的模型（阿里的复刻音色只能用复刻时的模型） |
| `params` | object | 平台参数，键名见 Provider 的 `tts_params` |
| `format`、`speed`、`volume`、`pitch`、`sample_rate`、`emotion`、`instruction`、`language` | | 快捷字段，会合并进 `params`；与 `params` 中的同名键冲突时以 `params` 为准 |
| `output` | `audio` / `url` / `base64` | 默认为 `audio` |
| `save` | bool | 默认 `true`，写入合成历史；`output=url` 时总会保存 |

参数合并顺序：平台默认值 → 音色的 `default_params` → 本次请求。请求的格式平台不支持时，回退到平台默认格式。

**`output=audio` 的响应**：响应体是音频二进制，`Content-Type` 为实际格式（如 `audio/mpeg`、`audio/wav`），响应头包括：
`X-Generation-Id`（`save=false` 时没有）、`X-Audio-Duration-Ms`、`X-Elapsed-Ms`、`X-Voice-Provider`、`X-Voice-Id`（URL 编码）。

**`output=url` / `output=base64` 的响应**：

```json
{
  "provider": "minimax", "voice_id": "VoxGentle01", "voice_name": "温柔知性女声",
  "format": "mp3", "duration_ms": 3120, "elapsed_ms": 1840,
  "audio_url": "/api/generations/42/audio",
  "generation": { "...": "Generation 对象" },
  "audio_base64": "仅 output=base64 时返回"
}
```

`audio_url` 是相对路径。在浏览器 `<audio>` 里播放时，需要拼上服务地址，并在启用鉴权时追加 `?api_key=`。

### `GET /api/tts`

查询参数：`voice`、`text`、`provider`、`model`、`format`、`speed`、`volume`、`pitch`、`params`（JSON 字符串）、`save`。直接返回音频，适合嵌入网页或物联网设备：

```
GET /api/tts?voice=12&text=你好&format=mp3&api_key=vd-xxx
```

## 合成历史

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/generations` | 分页列表：`page`（默认 1）、`page_size`（默认 20，最大 200）、`provider`、`voice_pk`（音色库 ID）、`q`（匹配文本、音色名）。返回 `{"items": [Generation], "total", "page", "page_size"}`，最新的在前 |
| `GET` | `/api/generations/{id}/audio` | 获取音频；`?download=true` 时以附件形式下载 |
| `DELETE` | `/api/generations/{id}` | 删除一条记录及其音频 |
| `DELETE` | `/api/generations` | 清空历史；`?voice_pk=` 时只清空该音色的记录。返回 `{"deleted": n}` |

## OpenAI 兼容

### `POST /v1/audio/speech`

请求体与 OpenAI TTS 相同：`input`（文本）、`voice`（写法同 `/api/tts`）、`model`（会被忽略；填 `volcengine` / `aliyun` / `minimax` / `zhipu` 时强制使用该平台）、`response_format`（mp3 / wav / flac / opus …，不支持 `pcm` 和 `aac`）、`speed`、`instructions`（对应 `instruction` 参数）。直接返回音频，鉴权方式与其他接口相同，可以直接用 OpenAI SDK 调用（`base_url` 设为 `{VOXDOCK_URL}/v1`）。

## 数据结构

**Voice**

```json
{
  "id": 12, "provider": "aliyun", "voice_id": "cosyvoice-v3-plus-myvoice-xxxx", "name": "我的声音",
  "description": "", "tags": ["女声"], "status": "ready", "status_message": "",
  "model": "cosyvoice-v3-plus", "language": "", "source": "clone",
  "favorite": false, "has_sample": true, "sample_text": "参考文本", "has_demo": true,
  "default_params": {"speed": 1.1}, "extra": {"reference_count": 2, "merged": true},
  "usage_count": 5, "last_used_at": "2026-01-01T12:00:00", "created_at": "…", "updated_at": "…"
}
```

- `status`：`ready`（可用）、`training`（训练或审核中）、`failed`（失败，原因在 `status_message`）、`unknown`
- `source`：`clone`（通过 VoxDock 复刻）、`manual`（手动添加）、`import`（从平台同步）

**Generation**

```json
{
  "id": 42, "voice_pk": 12, "provider": "aliyun", "voice_id": "…", "voice_name": "我的声音",
  "model": "cosyvoice-v3-plus", "text": "你好", "params": {"speed": 1.1, "format": "mp3"},
  "format": "mp3", "size_bytes": 23040, "duration_ms": 1440, "elapsed_ms": 980,
  "source": "api", "created_at": "…", "audio_url": "/api/generations/42/audio"
}
```

`source`：`api`、`web` 或 `openai`。
