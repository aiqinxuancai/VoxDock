"""Multiple reference clips: local merge with silence gaps."""
import asyncio
import base64
import io
import json
import re
import struct
import subprocess
import wave

import pytest
import respx

from app import audio as audio_mod
from app.audio import AudioError, merge_clips, wav_duration_ms, wav_to_pcm16

from .conftest import configure


def tone_wav(seconds: float, rate: int = 24000, channels: int = 1, width: int = 2, value: int = 3000) -> bytes:
    n = int(seconds * rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        if width == 2:
            frame = struct.pack("<h", value) * channels
        elif width == 1:
            frame = bytes([128 + (value >> 8)]) * channels
        else:  # 24/32-bit little endian, value placed in the top 16 bits
            frame = (b"\x00" * (width - 2) + struct.pack("<h", value)) * channels
        w.writeframes(frame * n)
    return buf.getvalue()


def merge(clips, gap=2.0):
    return asyncio.run(merge_clips(clips, gap))


def test_merge_same_rate_inserts_gap():
    wav, duration = merge([(tone_wav(1.0), "wav"), (tone_wav(0.5), "wav")])
    assert duration == 3500 and wav_duration_ms(wav) == 3500
    pcm, rate, channels = wav_to_pcm16(wav)
    assert (rate, channels) == (24000, 1)
    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
    assert samples[100] == 3000                              # first clip
    assert set(samples[24000:24000 + 48000]) == {0}          # 2s silence
    assert samples[24000 + 48000 + 10] == 3000               # second clip


def test_merge_mixed_rates_channels_and_widths():
    clips = [
        (tone_wav(1.0, rate=16000), "wav"),
        (tone_wav(1.0, rate=48000, channels=2), "wav"),
        (tone_wav(0.5, rate=22050, width=1, value=8192), "wav"),
        (tone_wav(0.5, rate=44100, width=3), "wav"),
    ]
    wav, duration = merge(clips, gap=1.0)
    pcm, rate, channels = wav_to_pcm16(wav)
    assert (rate, channels) == (24000, 1)
    assert abs(duration - (1000 + 1000 + 500 + 500 + 3 * 1000)) <= 5
    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
    assert samples[1000] == 3000                       # upsampled 16k clip keeps its level
    assert samples[24000 * 2 + 1000] == 3000           # stereo 48k clip downmixed + downsampled


def test_merge_non_wav_requires_ffmpeg(monkeypatch):
    monkeypatch.setattr(audio_mod, "ffmpeg_path", lambda: None)
    mp3 = b"ID3" + b"\x00" * 4000
    with pytest.raises(AudioError, match="ffmpeg"):
        merge([(tone_wav(0.5), "wav"), (mp3, "mp3")])


@pytest.mark.skipif(not audio_mod.ffmpeg_available(), reason="ffmpeg not installed")
def test_merge_with_ffmpeg_decodes_mp3():
    mp3 = subprocess.run(
        [audio_mod.ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-ac", "1", "-f", "mp3", "pipe:1"], capture_output=True, check=True).stdout
    wav, duration = merge([(tone_wav(1.0, rate=16000), "wav"), (mp3, "mp3")])
    assert wav_to_pcm16(wav)[1] == 24000
    assert 3900 <= duration <= 4200


def _multipart_wav(content: bytes) -> bytes:
    start = content.index(b"RIFF")
    size = struct.unpack("<I", content[start + 4:start + 8])[0]
    return content[start:start + 8 + size]


def test_clone_with_multiple_files_merges_for_single_clip_provider(client):
    assert client.get("/api/providers/minimax").json()["max_reference_audios"] == 1
    configure(client, "minimax", api_key="mm-key-123456789")
    with respx.mock() as mock:
        up = mock.post("https://api.minimax.cn/v1/files/upload").respond(
            json={"file": {"file_id": 1}, "base_resp": {"status_code": 0}})
        mock.post("https://api.minimax.cn/v1/voice_clone").respond(json={"base_resp": {"status_code": 0}})
        files = [("file", ("a.wav", tone_wav(1.0), "audio/wav")), ("file", ("b.wav", tone_wav(1.5, rate=48000), "audio/wav"))]
        r = client.post("/api/voices/clone", data={"provider": "minimax", "name": "多段"}, files=files)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["extra"]["reference_count"] == 2 and v["extra"]["merged"] is True
    assert v["extra"]["merge_gap_seconds"] == 2.0
    sent = _multipart_wav(up.calls[0].request.content)
    assert wav_duration_ms(sent) == 4500 and wav_to_pcm16(sent)[1] == 24000
    sample = client.get(f"/api/voices/{v['id']}/sample")
    assert sample.status_code == 200 and wav_duration_ms(sample.content) == 4500


def test_clone_multiple_files_volcengine_base64(client):
    configure(client, "volcengine", api_key="volc-key-123456789")
    with respx.mock() as mock:
        clone = mock.post("https://openspeech.bytedance.com/api/v3/tts/voice_clone").respond(json={"status": 2})
        files = [("file", (f"{i}.wav", tone_wav(0.5), "audio/wav")) for i in range(3)]
        r = client.post("/api/voices/clone", data={"provider": "volcengine", "name": "v", "voice_id": "S_x"}, files=files)
    assert r.status_code == 200, r.text
    body = json.loads(clone.calls[0].request.content)
    merged = base64.b64decode(body["audio"]["data"])
    assert body["audio"]["format"] == "wav" and wav_duration_ms(merged) == 500 * 3 + 2000 * 2


def test_single_file_is_not_merged(client):
    configure(client, "zhipu", api_key="zp-key-123456789")
    with respx.mock() as mock:
        up = mock.post("https://open.bigmodel.cn/api/paas/v4/files").respond(json={"id": "f1"})
        mock.post("https://open.bigmodel.cn/api/paas/v4/voice/clone").respond(json={"voice": "vc1"})
        r = client.post("/api/voices/clone", data={"provider": "zhipu", "name": "z"},
                        files={"file": ("a.wav", tone_wav(1.0, rate=16000), "audio/wav")})
    assert r.status_code == 200, r.text
    assert r.json()["extra"]["reference_count"] == 1 and "merged" not in r.json()["extra"]
    sent = _multipart_wav(up.calls[0].request.content)
    assert wav_to_pcm16(sent)[1] == 16000  # original clip passed through untouched


def test_clone_mixed_formats_without_ffmpeg_is_rejected(client, monkeypatch):
    monkeypatch.setattr(audio_mod, "ffmpeg_path", lambda: None)
    configure(client, "minimax", api_key="mm-key-123456789")
    files = [("file", ("a.wav", tone_wav(1.0), "audio/wav")), ("file", ("b.mp3", b"ID3" + b"\x00" * 4000, "audio/mpeg"))]
    r = client.post("/api/voices/clone", data={"provider": "minimax", "name": "x"}, files=files)
    assert r.status_code == 400 and re.search("第 2 段.*ffmpeg", r.json()["detail"])


def test_too_many_clips(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("VOXDOCK_MAX_REFERENCE_AUDIOS", "2")
    get_settings.cache_clear()
    configure(client, "minimax", api_key="mm-key-123456789")
    files = [("file", (f"{i}.wav", tone_wav(0.3), "audio/wav")) for i in range(3)]
    r = client.post("/api/voices/clone", data={"provider": "minimax", "name": "x"}, files=files)
    assert r.status_code == 400 and "最多 2 段" in r.json()["detail"]
