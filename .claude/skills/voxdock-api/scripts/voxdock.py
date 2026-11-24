#!/usr/bin/env python3
"""VoxDock API 命令行客户端（仅依赖 Python 标准库，Python 3.8+）。

连接配置（命令行参数优先）：
  VOXDOCK_URL      服务地址，默认 http://localhost:8000
  VOXDOCK_API_KEY  API Key（vd-...）；服务未设置管理员密码时可不填

示例：
  python voxdock.py health
  python voxdock.py voices --status ready
  python voxdock.py tts 3 "你好，欢迎使用 VoxDock" -o hello.mp3 --speed 1.1
  python voxdock.py tts minimax:male-qn-qingse "直接使用平台系统音色" -o sys.mp3
  python voxdock.py clone --provider minimax --name 我的声音 part1.wav part2.wav --wait
  python voxdock.py providers aliyun          # 查看某平台的模型、合成参数与复刻选项
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

AUDIO_EXT = {"audio/mpeg": "mp3", "audio/wav": "wav", "audio/x-wav": "wav", "audio/flac": "flac",
             "audio/ogg": "ogg", "audio/opus": "opus", "audio/aac": "aac", "audio/pcm": "pcm"}


class ApiError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(f"HTTP {status}: {detail}" if status else detail)
        self.status, self.detail = status, detail


class Client:
    def __init__(self, url: str, key: str = "", timeout: float = 300):
        self.url, self.key, self.timeout = url.rstrip("/"), key, timeout

    def request(self, method: str, path: str, *, query: dict | None = None, json_body=None,
                data: bytes | None = None, content_type: str | None = None, raw: bool = False):
        url = self.url + path
        if query:
            q = {k: v for k, v in query.items() if v is not None and v != ""}
            if q:
                url += "?" + urlencode({k: str(v).lower() if isinstance(v, bool) else v for k, v in q.items()})
        headers = {"Accept": "application/json, audio/*", "User-Agent": "voxdock-skill-cli"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        if json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode()
            content_type = "application/json"
        if content_type:
            headers["Content-Type"] = content_type
        req = Request(url, data=data, method=method, headers=headers)
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                body = resp.read()
                if raw:
                    return body, dict(resp.headers.items())
                return json.loads(body.decode() or "null")
        except HTTPError as e:
            text = e.read().decode(errors="replace")
            try:
                detail = json.loads(text).get("detail", text)
            except ValueError:
                detail = text or e.reason
            if isinstance(detail, list):  # FastAPI validation errors
                detail = "; ".join(f"{'.'.join(str(x) for x in d.get('loc', []))}: {d.get('msg')}" for d in detail)
            raise ApiError(e.code, str(detail)) from None
        except URLError as e:
            raise ApiError(0, f"无法连接 {self.url}：{e.reason}（检查 VOXDOCK_URL 与服务是否启动）") from None

    def multipart(self, path: str, fields: dict, files: list[str]):
        boundary = "----voxdock" + uuid.uuid4().hex
        parts: list[bytes] = []
        for k, v in fields.items():
            if v is None or v == "":
                continue
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        for path_ in files:
            name = os.path.basename(path_).replace('"', "%22").replace("\r", "").replace("\n", "")
            ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
            with open(path_, "rb") as f:
                content = f.read()
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
                         f"Content-Type: {ctype}\r\n\r\n".encode() + content + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        return self.request("POST", path, data=b"".join(parts), content_type=f"multipart/form-data; boundary={boundary}")


# ----------------------------------------------------------------- helpers
def parse_kv(items: list[str] | None) -> dict:
    """k=v pairs; values are parsed as JSON when possible (numbers, true/false, null, objects)."""
    out = {}
    for item in items or []:
        if "=" not in item:
            raise SystemExit(f"参数格式应为 key=value：{item}")
        k, v = item.split("=", 1)
        try:
            out[k.strip()] = json.loads(v)
        except ValueError:
            out[k.strip()] = v
    return out


def dump(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def fmt_ms(ms) -> str:
    if not ms:
        return "-"
    s = int(round(ms / 1000))
    return f"{s // 60}:{s % 60:02d}"


def voice_line(v: dict) -> str:
    flag = "★ " if v.get("favorite") else ""
    model = f" [{v['model']}]" if v.get("model") else ""
    msg = f" — {v['status_message']}" if v.get("status") != "ready" and v.get("status_message") else ""
    return f"{v['id']:>4}  {v['status']:<8} {v['provider']:<10} {flag}{v['name']}  ({v['voice_id']}){model}{msg}"


def output_path(requested: str | None, default_stem: str, ext: str) -> str:
    """Use the requested path, but make the extension match the audio actually returned."""
    if not requested:
        return f"{default_stem}.{ext}"
    stem, cur = os.path.splitext(requested)
    if ext != "bin" and cur.lower().lstrip(".") != ext:
        fixed = f"{stem}.{ext}"
        print(f"注意：平台实际返回 {ext} 格式（请求的格式不受支持时会回退到平台默认格式），已保存为 {fixed}", file=sys.stderr)
        return fixed
    return requested


def read_text(value: str | None, file: str | None) -> str:
    if file:
        with open(file, encoding="utf-8") as f:
            return f.read()
    if value == "-" or value is None:
        return sys.stdin.read()
    return value


# ---------------------------------------------------------------- commands
def cmd_health(c: Client, a) -> None:
    h = c.request("GET", "/healthz")
    auth = c.request("GET", "/api/auth/status")
    print(f"服务正常：{c.url}  版本 {h.get('version')}")
    if not auth.get("auth_enabled"):
        print("鉴权：未启用（无需 API Key）")
    elif auth.get("authenticated"):
        print("鉴权：已启用，API Key 有效")
    else:
        raise ApiError(401, "服务已启用鉴权，但未提供有效的 API Key")
    s = c.request("GET", "/api/system")
    print(f"ffmpeg：{'可用' if s.get('ffmpeg') else '不可用'}  参考音频最多 {s.get('max_reference_audios')} 段，"
          f"合并间隔 {s.get('merge_gap_seconds')} 秒，单文件 ≤{s.get('max_upload_mb')}MB")
    for p in c.request("GET", "/api/providers")["items"]:
        state = "就绪" if p["configured"] and p["enabled"] else ("已停用" if p["configured"] else "未配置")
        print(f"  {p['name']:<10} {p['label']:<8} {state}")


def cmd_providers(c: Client, a) -> None:
    if not a.name:
        items = c.request("GET", "/api/providers")["items"]
        if a.json:
            return dump(items)
        for p in items:
            state = "就绪" if p["configured"] and p["enabled"] else ("已停用" if p["configured"] else "未配置")
            print(f"{p['name']:<10} {p['label']:<8} {state}  默认模型 {p['default_model']}  文本上限 {p['max_text_length']}")
        return
    p = c.request("GET", f"/api/providers/{a.name}")
    if a.json:
        return dump(p)

    def field(f) -> str:
        bits = [f"{f['key']:<26}", f.get("type", "")]
        if f.get("default") not in (None, ""):
            bits.append(f"默认={f['default']}")
        if f.get("min") is not None or f.get("max") is not None:
            bits.append(f"范围={f.get('min')}~{f.get('max')}")
        if f.get("options"):
            vals = [str(o["value"]) for o in f["options"] if o["value"] != ""]
            bits.append("可选=" + ",".join(vals))
        if f.get("models"):
            bits.append("仅模型=" + ",".join(f["models"]))
        label = f.get("label", "") + (f"（{f['help']}）" if f.get("help") else "")
        return "  " + " ".join(bits) + "  # " + label

    print(f"{p['label']} ({p['name']})  {'已配置' if p['configured'] else '未配置'}  文本上限 {p['max_text_length']} 字符")
    print("模型：" + ", ".join(f"{m['value']}" + (" (默认)" if m["value"] == p["default_model"] else "") for m in p["models"]))
    print("\n合成参数（params / 快捷字段）：")
    for f in p["tts_params"]:
        print(field(f))
    vf = p.get("voice_id_field") or {}
    print(f"\n复刻：voice_id = {vf.get('label', '')}{'（必填）' if vf.get('required') else '（可选）'} {vf.get('help', '')}")
    formats = ", ".join(p.get("clone_audio_formats", []))
    print(f"  参考音频最多 {p.get('max_reference_audios', 1)} 条（超出时服务端合并），支持格式 {formats}"
          f"{'，支持 audio_url' if p['capabilities'].get('audio_url') else ''}")
    if p["clone_fields"]:
        print("  options（JSON）：")
        for f in p["clone_fields"]:
            print("  " + field(f))
    for tip in p.get("clone_tips", []):
        print(f"  · {tip}")


def cmd_voices(c: Client, a) -> None:
    items = c.request("GET", "/api/voices", query={"provider": a.provider, "status": a.status, "q": a.q,
                                                   "favorite": True if a.favorite else None})["items"]
    if a.json:
        return dump(items)
    if not items:
        print("（音色库为空）")
    for v in items:
        print(voice_line(v))


def cmd_voice(c: Client, a) -> None:
    dump(c.request("GET", f"/api/voices/{a.id}"))


def cmd_tts(c: Client, a) -> None:
    text = read_text(a.text, a.text_file).strip()
    params = parse_kv(a.param)
    body = {"voice": int(a.voice) if a.voice.isdigit() and not a.provider else a.voice, "text": text,
            "provider": a.provider, "model": a.model, "params": params, "save": not a.no_save, "output": "audio"}
    for k in ("format", "speed", "volume", "pitch", "sample_rate", "emotion", "instruction", "language"):
        if getattr(a, k) is not None:
            body[k] = getattr(a, k)
    body = {k: v for k, v in body.items() if v is not None}
    audio, headers = c.request("POST", "/api/tts", json_body=body, raw=True)
    h = {k.lower(): v for k, v in headers.items()}
    ext = AUDIO_EXT.get(h.get("content-type", "").split(";")[0], "bin")
    out = output_path(a.output, f"voxdock-{h.get('x-generation-id') or int(time.time())}", ext)
    with open(out, "wb") as f:
        f.write(audio)
    print(json.dumps({"file": os.path.abspath(out), "bytes": len(audio), "format": ext,
                      "duration_ms": int(h["x-audio-duration-ms"]) if h.get("x-audio-duration-ms") else None,
                      "elapsed_ms": int(h["x-elapsed-ms"]) if h.get("x-elapsed-ms") else None,
                      "generation_id": int(h["x-generation-id"]) if h.get("x-generation-id") else None,
                      "provider": h.get("x-voice-provider"), "voice_id": h.get("x-voice-id")}, ensure_ascii=False))


def wait_ready(c: Client, pk: int, timeout: float, interval: float = 5) -> dict:
    deadline = time.time() + timeout
    v = c.request("GET", f"/api/voices/{pk}")
    while v["status"] == "training" and time.time() < deadline:
        print(f"训练中… {v.get('status_message') or ''}", file=sys.stderr)
        time.sleep(interval)
        v = c.request("POST", f"/api/voices/{pk}/refresh")
    return v


def cmd_clone(c: Client, a) -> None:
    if not a.files and not a.audio_url:
        raise SystemExit("请提供参考音频文件，或使用 --audio-url")
    for f in a.files:
        if not os.path.isfile(f):
            raise SystemExit(f"文件不存在：{f}")
    fields = {"provider": a.provider, "name": a.name, "model": a.model, "voice_id": a.voice_id,
              "transcript": read_text(None, a.transcript_file) if a.transcript_file else a.transcript,
              "demo_text": a.demo_text, "description": a.description, "tags": a.tags,
              "options": json.dumps(parse_kv(a.option), ensure_ascii=False), "audio_url": a.audio_url}
    v = c.multipart("/api/voices/clone", fields, a.files)
    if a.wait and v["status"] == "training":
        v = wait_ready(c, v["id"], a.timeout)
    extra = v.get("extra") or {}
    print(voice_line(v))
    if extra.get("merged"):
        print(f"  {extra.get('reference_count')} 段参考音频已按顺序合并（间隔 {extra.get('merge_gap_seconds')} 秒，"
              f"共 {fmt_ms(extra.get('reference_duration_ms'))}）")
    if v["status"] == "training":
        print(f"  平台仍在训练/审核，稍后执行：python {os.path.basename(__file__)} wait {v['id']}")
    if a.json:
        dump(v)


def cmd_refresh(c: Client, a) -> None:
    print(voice_line(c.request("POST", f"/api/voices/{a.id}/refresh")))


def cmd_wait(c: Client, a) -> None:
    v = wait_ready(c, a.id, a.timeout)
    print(voice_line(v))
    if v["status"] != "ready":
        sys.exit(2)


def cmd_add(c: Client, a) -> None:
    v = c.request("POST", "/api/voices", json_body={"provider": a.provider, "voice_id": a.voice_id,
                                                    "name": a.name or "", "model": a.model or ""})
    print(voice_line(v))


def cmd_update(c: Client, a) -> None:
    body = {"name": a.name, "description": a.description, "model": a.model}
    if a.tags is not None:
        body["tags"] = [t.strip() for t in a.tags.split(",") if t.strip()]
    if a.favorite is not None:
        body["favorite"] = a.favorite == "true"
    if a.default_param:
        body["default_params"] = parse_kv(a.default_param)
    body = {k: v for k, v in body.items() if v is not None}
    print(voice_line(c.request("PATCH", f"/api/voices/{a.id}", json_body=body)))


def cmd_delete(c: Client, a) -> None:
    c.request("DELETE", f"/api/voices/{a.id}", query={"remote": a.remote or None, "force": a.force or None})
    print(f"已删除音色 {a.id}" + ("（含平台音色）" if a.remote else "（仅本地记录）"))


def cmd_sync(c: Client, a) -> None:
    r = c.request("POST", f"/api/providers/{a.provider}/sync")
    print(f"同步完成：平台共 {r['total']} 个，新增 {r['added']}，更新 {r['updated']}")


def cmd_history(c: Client, a) -> None:
    r = c.request("GET", "/api/generations", query={"page_size": a.limit, "provider": a.provider,
                                                    "voice_pk": a.voice, "q": a.q})
    if a.json:
        return dump(r)
    for g in r["items"]:
        text = g["text"].replace("\n", " ")
        print(f"{g['id']:>5}  {g['created_at'][:19]}  {g['provider']:<10} {g['voice_name'][:16]:<16} "
              f"{fmt_ms(g['duration_ms']):>5} {g['format']:<4} {text[:40]}{'…' if len(text) > 40 else ''}")
    print(f"（共 {r['total']} 条；下载：GET {c.url}/api/generations/<id>/audio）")


def cmd_download(c: Client, a) -> None:
    audio, headers = c.request("GET", f"/api/generations/{a.id}/audio", raw=True)
    ext = AUDIO_EXT.get({k.lower(): v for k, v in headers.items()}.get("content-type", "").split(";")[0], "bin")
    out = output_path(a.output, f"voxdock-{a.id}", ext)
    with open(out, "wb") as f:
        f.write(audio)
    print(os.path.abspath(out))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="voxdock.py", description="VoxDock API 命令行客户端",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("示例：")[1])
    p.add_argument("--url", default=os.environ.get("VOXDOCK_URL", "http://localhost:8000"), help="服务地址（VOXDOCK_URL）")
    p.add_argument("--key", default=os.environ.get("VOXDOCK_API_KEY", ""), help="API Key（VOXDOCK_API_KEY）")
    p.add_argument("--timeout", type=float, default=300, help="请求超时秒数，默认 300")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="<command>")

    s = sub.add_parser("health", help="检查服务、鉴权、平台配置状态")
    s.set_defaults(fn=cmd_health)

    s = sub.add_parser("providers", help="平台列表；指定平台名时列出模型、合成参数与复刻选项")
    s.add_argument("name", nargs="?", choices=["volcengine", "aliyun", "minimax", "zhipu"])
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_providers)

    s = sub.add_parser("voices", help="音色列表")
    s.add_argument("--provider")
    s.add_argument("--status", choices=["ready", "training", "failed", "unknown"])
    s.add_argument("-q", help="按名称 / 音色 ID / 描述搜索")
    s.add_argument("--favorite", action="store_true", help="只看收藏")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_voices)

    s = sub.add_parser("voice", help="音色详情（JSON）")
    s.add_argument("id", type=int)
    s.set_defaults(fn=cmd_voice)

    s = sub.add_parser("tts", help="合成语音并保存为文件")
    s.add_argument("voice", help="音色库 ID / 平台音色 ID / 音色名称 / provider:voice_id")
    s.add_argument("text", nargs="?", help="合成文本；'-' 或省略时从标准输入读取")
    s.add_argument("--text-file", help="从 UTF-8 文本文件读取")
    s.add_argument("-o", "--output", help="输出文件，默认 voxdock-<历史ID>.<格式>")
    s.add_argument("--provider", help="voice 为平台原始 ID 时指定平台")
    s.add_argument("--model", help="覆盖音色绑定的模型")
    s.add_argument("--format")
    s.add_argument("--speed", type=float)
    s.add_argument("--volume", type=float)
    s.add_argument("--pitch", type=float)
    s.add_argument("--sample-rate", dest="sample_rate", type=int)
    s.add_argument("--emotion")
    s.add_argument("--instruction")
    s.add_argument("--language")
    s.add_argument("--param", action="append", metavar="K=V", help="平台参数，可重复，如 --param bitrate=64000")
    s.add_argument("--no-save", action="store_true", help="不写入合成历史")
    s.set_defaults(fn=cmd_tts)

    s = sub.add_parser("clone", help="上传参考音频复刻新音色（可传多个文件）")
    s.add_argument("files", nargs="*", help="参考音频文件，按顺序合并")
    s.add_argument("--provider", required=True, choices=["volcengine", "aliyun", "minimax", "zhipu"])
    s.add_argument("--name", required=True, help="音色显示名称")
    s.add_argument("--model", default="")
    s.add_argument("--voice-id", default="", help="平台音色 ID / 前缀；火山必填（S_xxx）")
    s.add_argument("--transcript", default="", help="参考音频对应文本（多段按顺序拼接）")
    s.add_argument("--transcript-file")
    s.add_argument("--demo-text", default="", help="试听文本")
    s.add_argument("--description", default="")
    s.add_argument("--tags", default="", help="逗号分隔")
    s.add_argument("--option", action="append", metavar="K=V", help="平台复刻选项，可重复，见 providers <name>")
    s.add_argument("--audio-url", default="", help="公网音频 URL（阿里云支持）")
    s.add_argument("--wait", action="store_true", help="训练/审核中时轮询直到完成")
    s.add_argument("--json", action="store_true", help="输出完整音色 JSON")
    s.set_defaults(fn=cmd_clone)

    s = sub.add_parser("refresh", help="向平台查询一次音色状态")
    s.add_argument("id", type=int)
    s.set_defaults(fn=cmd_refresh)

    s = sub.add_parser("wait", help="轮询直到音色训练完成（失败时退出码 2）")
    s.add_argument("id", type=int)
    s.set_defaults(fn=cmd_wait)

    s = sub.add_parser("add", help="把已有的平台音色 / 系统音色加入音色库")
    s.add_argument("provider", choices=["volcengine", "aliyun", "minimax", "zhipu"])
    s.add_argument("voice_id")
    s.add_argument("--name")
    s.add_argument("--model")
    s.set_defaults(fn=cmd_add)

    s = sub.add_parser("update", help="编辑音色（名称/标签/收藏/默认参数）")
    s.add_argument("id", type=int)
    s.add_argument("--name")
    s.add_argument("--description")
    s.add_argument("--model")
    s.add_argument("--tags", help="逗号分隔，整体替换")
    s.add_argument("--favorite", choices=["true", "false"])
    s.add_argument("--default-param", action="append", metavar="K=V", help="默认合成参数（整体替换），可重复")
    s.set_defaults(fn=cmd_update)

    s = sub.add_parser("delete", help="删除音色")
    s.add_argument("id", type=int)
    s.add_argument("--remote", action="store_true", help="同时删除平台上的音色（不可恢复）")
    s.add_argument("--force", action="store_true", help="平台删除失败时仍删除本地记录")
    s.set_defaults(fn=cmd_delete)

    s = sub.add_parser("sync", help="从平台同步音色到音色库")
    s.add_argument("provider", choices=["volcengine", "aliyun", "minimax", "zhipu"])
    s.set_defaults(fn=cmd_sync)

    s = sub.add_parser("history", help="合成历史")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--provider")
    s.add_argument("--voice", type=int, help="音色库 ID")
    s.add_argument("-q", help="按文本 / 音色名搜索")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_history)

    s = sub.add_parser("download", help="下载历史音频")
    s.add_argument("id", type=int)
    s.add_argument("-o", "--output")
    s.set_defaults(fn=cmd_download)
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    a = build_parser().parse_args(argv)
    client = Client(a.url, a.key, a.timeout)
    try:
        a.fn(client, a)
    except ApiError as e:
        print(f"错误：{e}", file=sys.stderr)
        if e.status == 401:
            print("提示：服务已启用鉴权，请设置 VOXDOCK_API_KEY（在 Web「API 接入」页面创建）", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
