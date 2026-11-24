# 各平台的模型与参数

本文是编写时的快照。服务端的实际定义以 `GET /api/providers/{name}` 为准，也可以运行 `python scripts/voxdock.py providers <name>` 查看。合成参数放在 `/api/tts` 的 `params` 里（或使用快捷字段）；复刻选项以 JSON 格式放在 `/api/voices/clone` 的 `options` 字段里。

## 速览

| | 火山引擎 `volcengine` | 阿里云百炼 `aliyun` | MiniMax `minimax` | 智谱 `zhipu` |
| --- | --- | --- | --- | --- |
| 默认模型 | `seed-icl-2.0` | `cosyvoice-v3-plus` | `speech-2.8-hd` | `glm-tts` |
| 单次文本上限 | 5000 | 2000 | 10000 | 1024 |
| 复刻 `voice_id` | **必填**，控制台购买的 `S_xxx` | 可选，音色前缀 | 可选，自定义 ID | 可选，音色名称 |
| 复刻后的状态 | 训练中 → 可用 | CosyVoice / Qwen-Audio 审核中 → 可用；Qwen3-TTS-VC 直接可用 | 直接可用 | 直接可用 |
| 参考音频 | 10~30 秒，≤10MB | 10~20 秒，≤10MB，支持 `audio_url` | 10 秒~5 分钟，≤20MB | 3~30 秒，mp3/wav，≤10MB |
| 列出平台音色 / 删除平台音色 | ✅ / — | ✅ / ✅ | ✅ / ✅ | ✅ / ✅ |
| 输出格式 | mp3、wav、ogg_opus | mp3、wav、opus（Qwen3-TTS-VC 为 wav） | mp3、wav、flac | 仅 wav |

参考音频超过一条时，服务端会合并成一条（每段间隔 2 秒），合并后的总时长也要符合上表。

## 火山引擎 `volcengine`

模型：`seed-icl-2.0`（声音复刻 2.0）、`seed-icl-1.0`、`seed-icl-1.0-concurr`（1.0 并发版）。

合成参数：

| 键 | 类型 | 默认 | 范围 / 可选值 | 说明 |
| --- | --- | --- | --- | --- |
| `speed` | 数值 | 1.0 | 0.5~2.0 | 语速倍数 |
| `volume` | 数值 | 1.0 | 0.5~2.0 | 音量倍数 |
| `pitch` | 数值 | 0 | -12~12 | 音调，单位为半音 |
| `format` | 选项 | mp3 | mp3、wav、ogg_opus | 请求 `ogg` / `opus` 时自动映射为 ogg_opus |
| `sample_rate` | 选项 | 24000 | 8000~48000 | |
| `tts_model` | 选项 | 空 | `seed-tts-2.0-standard`、`seed-tts-2.0-expressive` | 仅 `seed-icl-2.0` 音色可用 |
| `language` | 选项 | 自动 | zh-cn、en、ja、ko、es-mx、id、pt-br、de、fr | 朗读语种 |
| `silence_duration` | 数值 | — | 0~30000 | 句尾静音，单位为毫秒 |

复刻选项（`options`）：`language`（参考音频的语种：0 中文、1 英语、2 日语、3 西班牙语、4 印尼语、5 葡萄牙语、6 德语、7 法语、8 韩语）、`enable_audio_denoise`（降噪）、`voice_clone_enable_mss`（背景音分离）、`custom_id`（后付费账号开启后，`voice_id` 作为自定义 ID 提交）、`disable_volume_normalization`、`enable_crop_by_asr`。

说明：火山没有「列出全部音色」的接口，`sync` 只会逐个查询管理员在平台配置里填写的已购音色 ID。

## 阿里云百炼 `aliyun`

模型：`cosyvoice-v3-plus`、`cosyvoice-v3-flash`、`cosyvoice-v3.5-plus`、`cosyvoice-v3.5-flash`、`qwen-audio-3.1-tts-plus`、`qwen-audio-3.1-tts-flash`、`qwen-audio-3.0-tts-plus`、`qwen-audio-3.0-tts-flash`、`qwen3-tts-vc-2026-01-22`。

**复刻的音色与模型绑定**：合成时只能用复刻时选择的模型，不要给这类音色传其他 `model`。

CosyVoice / Qwen-Audio 系列的合成参数：

| 键 | 类型 | 默认 | 范围 / 可选值 | 说明 |
| --- | --- | --- | --- | --- |
| `speed` | 数值 | 1.0 | 0.5~2.0 | 语速倍数 |
| `volume` | 数值 | **50** | **0~100** | 音量（注意不是倍数） |
| `pitch` | 数值 | **1.0** | **0.5~2.0** | 音调倍数（注意不是半音） |
| `format` | 选项 | mp3 | mp3、wav、opus | |
| `sample_rate` | 选项 | 24000 | 8000~48000 | |
| `instruction` | 文本 | — | ≤100 字符 | 用自然语言控制情感、方言、角色，部分模型和音色支持 |
| `language` | 选项 | 自动 | zh、en、ja、ko、fr、de、ru、pt、es、it、th、id、vi … | 目标语种 |
| `seed` | 数值 | — | 0~65535 | 随机种子，便于复现 |

Qwen3-TTS-VC（`qwen3-tts-vc-*`）固定输出 24kHz wav，合成参数只有 `language_type`：Auto（默认）、Chinese、English、Japanese、Korean、German、French、Russian、Italian、Spanish、Portuguese。

复刻选项（仅 CosyVoice / Qwen-Audio 系列）：`language`（参考音频语种，默认 zh）、`enable_preprocess`（降噪和音量均衡，`cosyvoice-v3-plus` 不支持）、`max_prompt_audio_length`（最大参考时长，3~30 秒）。`voice_id` 是音色前缀：CosyVoice / Qwen-Audio 为字母和数字，≤10 位；Qwen3-TTS-VC 为字母、数字和下划线，≤16 位。

## MiniMax `minimax`

模型：`speech-2.8-hd`、`speech-2.8-turbo`、`speech-2.6-hd`、`speech-2.6-turbo`、`speech-02-hd`、`speech-02-turbo`、`speech-01-hd`、`speech-01-turbo`。MiniMax 的音色不绑定模型，可以用 `params.model` 为单次合成指定模型。

合成参数：

| 键 | 类型 | 默认 | 范围 / 可选值 | 说明 |
| --- | --- | --- | --- | --- |
| `model` | 选项 | 音色的模型 | 见上 | 单次合成使用的模型 |
| `speed` | 数值 | 1.0 | 0.5~2.0 | |
| `volume` | 数值 | 1.0 | 0.1~10 | |
| `pitch` | 数值 | 0 | -12~12 | 半音 |
| `emotion` | 选项 | 自动 | happy、sad、angry、fearful、disgusted、surprised、calm、fluent、whisper | 情绪 |
| `format` | 选项 | mp3 | mp3、wav、flac | |
| `sample_rate` | 选项 | 32000 | 8000~44100 | |
| `bitrate` | 选项 | 128000 | 32000、64000、128000、256000 | 比特率 |
| `language_boost` | 选项 | — | auto、Chinese、Chinese,Yue、English、Japanese、Korean … | 语种增强 |
| `modify_pitch` / `intensity` / `timbre` | 数值 | 0 | -100~100 | 音色微调：低沉↔明亮、力量感、磁性↔清脆 |
| `sound_effects` | 选项 | — | spacious_echo、auditorium_echo、lofi_telephone、robotic | 音效 |

复刻选项：`need_noise_reduction`、`need_volume_normalization`、`language_boost`、`validate_text`（用 `transcript` 做 ASR 相似度校验）、`accuracy`（校验阈值，0~1，默认 0.7）。`voice_id` 为 8~256 位，以字母开头，可包含数字、`-` 和 `_`。

注意：复刻的音色需要在 7 天内用于正式合成，否则会被平台删除；首次合成后才会出现在平台的音色列表中。系统音色可以直接用 `minimax:<voice_id>` 合成，例如 `minimax:male-qn-qingse`。

## 智谱 AI `zhipu`

模型：`glm-tts`（复刻使用 `glm-tts-clone`，由服务端自动处理）。

合成参数：

| 键 | 类型 | 默认 | 范围 | 说明 |
| --- | --- | --- | --- | --- |
| `speed` | 数值 | 1.0 | 0.5~2.0 | |
| `volume` | 数值 | 1.0 | 0.1~10 | |
| `format` | 选项 | wav | 仅 wav | 请求其他格式时回退为 wav |
| `watermark_enabled` | 开关 | true | | AI 水印，仅已在智谱控制台申请去水印的账号可以关闭 |

智谱没有音调参数，也没有复刻选项。复刻时会用 `demo_text` 生成一段试听音频，填写 `transcript` 可以提升复刻效果。系统音色示例：`zhipu:tongtong`。
