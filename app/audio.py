"""Audio helpers: format detection, PCM->WAV wrapping, optional ffmpeg conversion."""
from __future__ import annotations

import asyncio
import io
import os
import shutil
import struct
import sys
import tempfile
import wave
from array import array
from pathlib import Path

MIME_TYPES = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "ogg": "audio/ogg",
    "ogg_opus": "audio/ogg",
    "opus": "audio/ogg",
    "flac": "audio/flac",
    "m4a": "audio/mp4",
    "aac": "audio/aac",
    "webm": "audio/webm",
    "pcm": "audio/L16",
}

FILE_EXT = {"ogg_opus": "ogg", "opus": "ogg"}


class AudioError(ValueError):
    pass


def mime_for(fmt: str) -> str:
    return MIME_TYPES.get(fmt, "application/octet-stream")


def ext_for(fmt: str) -> str:
    return FILE_EXT.get(fmt, fmt)


def detect_format(data: bytes, filename: str | None = None) -> str:
    """Detect audio container from magic bytes, falling back to file extension."""
    head = data[:16]
    if head[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0 and (head[1] & 0x06) != 0):
        return "mp3"
    if head[:4] == b"OggS":
        return "ogg"
    if head[:4] == b"fLaC":
        return "flac"
    if data[4:8] == b"ftyp":
        return "m4a"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    if len(head) > 1 and head[0] == 0xFF and (head[1] & 0xF6) == 0xF0:
        return "aac"
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext in MIME_TYPES:
            return ext
    return "unknown"


def pcm_to_wav(pcm: bytes, sample_rate: int = 24000, channels: int = 1, bits: int = 16) -> bytes:
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, channels, sample_rate, byte_rate, block_align, bits)
    header += b"data" + struct.pack("<I", len(pcm))
    return header + pcm


def wav_duration_ms(data: bytes) -> int | None:
    """Duration of a PCM WAV file by walking its chunks."""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    pos, byte_rate = 12, None
    while pos + 8 <= len(data):
        cid = data[pos : pos + 4]
        size = struct.unpack("<I", data[pos + 4 : pos + 8])[0]
        if cid == b"fmt " and pos + 20 <= len(data):
            byte_rate = struct.unpack("<I", data[pos + 16 : pos + 20])[0]
        elif cid == b"data" and byte_rate:
            # streaming WAVs may carry a bogus size (0 / 0xFFFFFFFF)
            real = min(size, len(data) - pos - 8) if size not in (0, 0xFFFFFFFF) else len(data) - pos - 8
            return int(real * 1000 / byte_rate)
        pos += 8 + size + (size & 1)
    return None


_MP3_KBPS = {
    "v1": [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0],
    "v2": [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0],
}


def mp3_duration_ms(data: bytes) -> int | None:
    """Estimate CBR MP3 (Layer III) duration from the first frame header."""
    pos = 0
    if data[:3] == b"ID3" and len(data) > 10:
        pos = 10 + ((data[6] & 0x7F) << 21 | (data[7] & 0x7F) << 14 | (data[8] & 0x7F) << 7 | (data[9] & 0x7F))
    end = min(len(data) - 4, pos + 65536)
    while pos < end:
        if data[pos] == 0xFF and (data[pos + 1] & 0xE0) == 0xE0:
            version = (data[pos + 1] >> 3) & 3  # 3=MPEG1, 2=MPEG2, 0=MPEG2.5
            layer = (data[pos + 1] >> 1) & 3  # 1=Layer III
            idx = (data[pos + 2] >> 4) & 0xF
            if layer == 1 and version != 1 and idx not in (0, 15):
                kbps = _MP3_KBPS["v1" if version == 3 else "v2"][idx]
                return int((len(data) - pos) * 8 / kbps)
        pos += 1
    return None


def estimate_duration_ms(data: bytes, fmt: str) -> int | None:
    if fmt == "wav":
        return wav_duration_ms(data)
    if fmt == "mp3":
        return mp3_duration_ms(data)
    return None


def ffmpeg_path() -> str | None:
    """ffmpeg on PATH, or ffmpeg.exe placed next to VoxDock.exe / in the working directory (Windows)."""
    if os.name == "nt":
        dirs = [Path(sys.executable).resolve().parent] if getattr(sys, "frozen", False) else []
        for d in [*dirs, Path.cwd()]:
            if (d / "ffmpeg.exe").is_file():
                return str(d / "ffmpeg.exe")
    return shutil.which("ffmpeg")


def ffmpeg_available() -> bool:
    return ffmpeg_path() is not None


async def _run_ffmpeg(data: bytes, output_args: list[str]) -> bytes:
    """Run ffmpeg on ``data`` (via a temp file, so seek-dependent containers like m4a work) -> stdout bytes."""
    exe = ffmpeg_path()
    if not exe:
        raise AudioError("服务器未安装 ffmpeg，无法转换音频格式，请上传 wav/mp3 文件")
    fd, src = tempfile.mkstemp(prefix="voxdock-", suffix=".audio")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        proc = await asyncio.create_subprocess_exec(
            exe, "-hide_banner", "-loglevel", "error", "-i", src, *output_args, "pipe:1",
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
    finally:
        try:
            os.unlink(src)
        except OSError:
            pass
    if proc.returncode != 0 or not out:
        raise AudioError(f"音频转换失败: {err.decode(errors='ignore')[:300]}")
    return out


async def convert_audio(data: bytes, target: str = "wav", sample_rate: int | None = None) -> bytes:
    """Convert audio to mono ``target`` via ffmpeg."""
    args = ["-ac", "1"]
    if sample_rate:
        args += ["-ar", str(sample_rate)]
    if target == "wav":
        args += ["-acodec", "pcm_s16le", "-f", "wav"]
    elif target == "mp3":
        args += ["-acodec", "libmp3lame", "-b:a", "192k", "-f", "mp3"]
    else:
        args += ["-f", target]
    return await _run_ffmpeg(data, args)


# ---------------------------------------------------------------- merging
MERGE_SAMPLE_RATE = 24000


def wav_to_pcm16(data: bytes) -> tuple[bytes, int, int] | None:
    """Parse an integer-PCM WAV into (16-bit little-endian PCM, sample_rate, channels); None if unsupported."""
    try:
        with wave.open(io.BytesIO(data)) as w:
            channels, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
            frames = w.readframes(w.getnframes())
    except (wave.Error, EOFError, ValueError):
        return None
    if width == 2:
        pcm = frames
    elif width == 1:  # unsigned 8-bit
        pcm = array("h", ((b - 128) << 8 for b in frames)).tobytes()
    elif width in (3, 4):  # keep the most significant 16 bits
        pcm = b"".join(frames[i + width - 2:i + width] for i in range(0, len(frames) - width + 1, width))
    else:
        return None
    return pcm[: len(pcm) - len(pcm) % (2 * channels)], rate, channels


def pcm16_to_mono(pcm: bytes, channels: int) -> bytes:
    if channels <= 1:
        return pcm
    a = array("h")
    a.frombytes(pcm)
    if channels == 2:
        return array("h", ((left + right) >> 1 for left, right in zip(a[0::2], a[1::2], strict=False))).tobytes()
    return array("h", (sum(a[i:i + channels]) // channels for i in range(0, len(a), channels))).tobytes()


def resample_pcm16(pcm: bytes, src: int, dst: int) -> bytes:
    """Mono 16-bit resampling: box-average when downsampling, linear interpolation when upsampling."""
    if src == dst or not pcm:
        return pcm
    a = array("h")
    a.frombytes(pcm)
    n = len(a)
    out_len = max(1, int(n * dst / src))
    step = src / dst
    if step >= 1:
        out = array("h", (
            sum(a[s:e]) // (e - s)
            for s, e in ((int(i * step), max(int(i * step) + 1, min(n, int((i + 1) * step)))) for i in range(out_len))
        ))
    else:
        last = n - 1
        vals = []
        for i in range(out_len):
            pos = i * step
            j = int(pos)
            vals.append(a[last] if j >= last else int(a[j] + (a[j + 1] - a[j]) * (pos - j)))
        out = array("h", vals)
    return out.tobytes()


async def merge_clips(
    clips: list[tuple[bytes, str]], gap_seconds: float = 2.0, target_rate: int = MERGE_SAMPLE_RATE
) -> tuple[bytes, int]:
    """Concatenate clips into one mono 16-bit WAV with ``gap_seconds`` of silence between them.

    Integer-PCM WAVs are merged in pure Python; other containers are decoded with ffmpeg.
    Returns (wav_bytes, duration_ms).
    """
    if not clips:
        raise AudioError("没有可合并的音频")
    decoded: list[tuple[bytes, int]] = []
    for idx, (data, fmt) in enumerate(clips, 1):
        parsed = wav_to_pcm16(data) if fmt == "wav" else None
        if parsed is not None:
            pcm, rate, channels = parsed
            decoded.append((await asyncio.to_thread(pcm16_to_mono, pcm, channels), rate))
            continue
        if not ffmpeg_available():
            raise AudioError(f"第 {idx} 段音频为 {fmt} 格式，合并多段非 WAV 音频需要 ffmpeg；请上传 wav 文件或使用网页录音")
        pcm = await _run_ffmpeg(data, ["-ac", "1", "-ar", str(target_rate), "-acodec", "pcm_s16le", "-f", "s16le"])
        decoded.append((pcm, target_rate))
    rates = {rate for _, rate in decoded}
    out_rate = rates.pop() if len(rates) == 1 else target_rate
    parts = [await asyncio.to_thread(resample_pcm16, pcm, rate, out_rate) for pcm, rate in decoded]
    silence = b"\x00\x00" * int(round(out_rate * max(0.0, gap_seconds)))
    pcm = silence.join(parts)
    return pcm_to_wav(pcm, out_rate), int(len(pcm) / 2 * 1000 / out_rate)


async def ensure_format(data: bytes, fmt: str, allowed: list[str]) -> tuple[bytes, str]:
    """Return audio in one of ``allowed`` formats, converting to wav when needed."""
    if fmt in allowed:
        return data, fmt
    target = "wav" if "wav" in allowed else allowed[0]
    return await convert_audio(data, target), target


def save_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
