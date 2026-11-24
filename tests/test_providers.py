"""Provider integrations against mocked platform APIs."""
import base64
import json

import httpx
import respx

from .conftest import configure, make_wav


def test_minimax_clone_and_tts(client, wav):
    configure(client, "minimax", api_key="mm-key-123456789")
    with respx.mock(assert_all_called=True) as mock:
        up = mock.post("https://api.minimax.cn/v1/files/upload").respond(
            json={"file": {"file_id": 998877}, "base_resp": {"status_code": 0}})
        clone = mock.post("https://api.minimax.cn/v1/voice_clone").respond(
            json={"demo_audio": "https://cdn.example.com/demo.mp3", "base_resp": {"status_code": 0}})
        mock.get("https://cdn.example.com/demo.mp3").respond(content=b"ID3" + b"\x00" * 2000)
        r = client.post("/api/voices/clone", data={"provider": "minimax", "name": "测试", "voice_id": "VoxTest001",
                                                   "demo_text": "你好", "options": json.dumps({"need_noise_reduction": True})},
                        files={"file": ("a.wav", wav, "audio/wav")})
        assert r.status_code == 200, r.text
        v = r.json()
        assert v["voice_id"] == "VoxTest001" and v["status"] == "ready" and v["has_demo"]
        body = json.loads(clone.calls[0].request.content)
        assert body["file_id"] == 998877 and body["need_noise_reduction"] is True
        assert body["text"] == "你好" and body["model"] == "speech-2.8-hd"
        assert b'name="purpose"' in up.calls[0].request.content

    audio = b"ID3fakeaudio"
    with respx.mock() as mock:
        t2a = mock.post("https://api.minimax.cn/v1/t2a_v2").respond(json={
            "data": {"audio": audio.hex(), "status": 2},
            "extra_info": {"audio_length": 1500, "audio_sample_rate": 32000},
            "base_resp": {"status_code": 0},
        })
        r = client.post("/api/tts", json={"voice": v["id"], "text": "合成测试", "speed": 1.3,
                                          "params": {"emotion": "happy", "intensity": 20}})
        assert r.status_code == 200, r.text
        assert r.content == audio and r.headers["content-type"] == "audio/mpeg"
        assert r.headers["x-audio-duration-ms"] == "1500"
        body = json.loads(t2a.calls[0].request.content)
        assert body["voice_setting"] == {"voice_id": "VoxTest001", "speed": 1.3, "vol": 1.0, "pitch": 0, "emotion": "happy"}
        assert body["voice_modify"] == {"intensity": 20}
        assert body["audio_setting"]["format"] == "mp3"

    hist = client.get("/api/generations").json()
    assert hist["total"] == 1 and hist["items"][0]["duration_ms"] == 1500
    a = client.get(hist["items"][0]["audio_url"])
    assert a.status_code == 200 and a.content == audio


def test_minimax_error_is_reported(client):
    configure(client, "minimax", api_key="mm-key-123456789")
    client.post("/api/voices", json={"provider": "minimax", "voice_id": "male-qn-qingse"})
    with respx.mock() as mock:
        mock.post("https://api.minimax.cn/v1/t2a_v2").respond(json={"base_resp": {"status_code": 1004, "status_msg": "login fail"}})
        r = client.post("/api/tts", json={"voice": "male-qn-qingse", "text": "hi"})
    assert r.status_code == 400
    assert "1004" in r.json()["detail"] and "login fail" in r.json()["detail"]


def test_aliyun_cosyvoice_clone_and_tts(client, wav):
    configure(client, "aliyun", api_key="sk-ali-123456789")
    base = "https://dashscope.aliyuncs.com/api/v1/services"

    def enroll(request):
        body = json.loads(request.content)
        action = body["input"]["action"]
        if action == "create_voice":
            assert body["model"] == "voice-enrollment"
            assert body["input"]["audio"].startswith("data:audio/wav;base64,")
            assert body["input"]["prefix"] == "myvoice"
            assert body["input"]["language_hints"] == ["zh"]
            return httpx.Response(200, json={"output": {"voice_id": "cosyvoice-v3-plus-myvoice-abc"}})
        assert action == "query_voice"
        return httpx.Response(200, json={"output": {"status": "OK", "target_model": "cosyvoice-v3-plus"}})

    with respx.mock() as mock:
        mock.post(f"{base}/audio/tts/customization").mock(side_effect=enroll)
        r = client.post("/api/voices/clone", data={"provider": "aliyun", "name": "阿里", "voice_id": "MyVoice",
                                                   "options": json.dumps({"language": "zh"})},
                        files={"file": ("a.wav", wav, "audio/wav")})
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["voice_id"] == "cosyvoice-v3-plus-myvoice-abc" and v["status"] == "ready" and v["model"] == "cosyvoice-v3-plus"

    with respx.mock() as mock:
        synth = mock.post(f"{base}/audio/tts/SpeechSynthesizer").respond(
            json={"output": {"audio": {"data": "", "url": "https://oss.example.com/a.mp3"}}, "usage": {"characters": 2}})
        mock.get("https://oss.example.com/a.mp3").respond(content=b"ID3audio")
        r = client.post("/api/tts", json={"voice": v["id"], "text": "你好", "params": {"volume": 70, "instruction": "开心"}})
    assert r.status_code == 200, r.text
    assert r.content == b"ID3audio"
    inp = json.loads(synth.calls[0].request.content)["input"]
    assert inp["voice"] == "cosyvoice-v3-plus-myvoice-abc" and inp["volume"] == 70 and inp["instruction"] == "开心"
    assert inp["rate"] == 1.0 and inp["format"] == "mp3"


def test_aliyun_qwen3_vc_clone_and_tts(client, wav):
    configure(client, "aliyun", api_key="sk-ali-123456789")
    base = "https://dashscope.aliyuncs.com/api/v1/services"
    with respx.mock() as mock:
        enroll = mock.post(f"{base}/audio/tts/customization").respond(
            json={"output": {"voice": "qwen-tts-vc-guanyu-voice-123", "target_model": "qwen3-tts-vc-2026-01-22"}})
        r = client.post("/api/voices/clone", data={"provider": "aliyun", "name": "千问", "voice_id": "guan_yu",
                                                   "model": "qwen3-tts-vc-2026-01-22", "transcript": "参考文本"},
                        files={"file": ("a.wav", wav, "audio/wav")})
    assert r.status_code == 200, r.text
    body = json.loads(enroll.calls[0].request.content)
    assert body["model"] == "qwen-voice-enrollment" and body["input"]["action"] == "create"
    assert body["input"]["preferred_name"] == "guan_yu" and body["input"]["text"] == "参考文本"
    assert body["input"]["audio"]["data"].startswith("data:audio/wav;base64,")
    v = r.json()
    assert v["status"] == "ready" and v["extra"]["family"] == "qwen-vc"

    with respx.mock() as mock:
        gen = mock.post(f"{base}/aigc/multimodal-generation/generation").respond(
            json={"output": {"audio": {"url": "https://oss.example.com/q.wav"}}})
        mock.get("https://oss.example.com/q.wav").respond(content=make_wav(0.5))
        r = client.post("/api/tts", json={"voice": v["id"], "text": "你好", "params": {"language_type": "Chinese"}, "output": "url"})
    assert r.status_code == 200, r.text
    assert r.json()["format"] == "wav" and r.json()["duration_ms"] == 500
    assert json.loads(gen.calls[0].request.content) == {
        "model": "qwen3-tts-vc-2026-01-22", "input": {"text": "你好", "voice": "qwen-tts-vc-guanyu-voice-123", "language_type": "Chinese"}}


def test_volcengine_clone_and_stream_tts(client, wav):
    configure(client, "volcengine", api_key="volc-key-123456789")
    base = "https://openspeech.bytedance.com/api/v3/tts"
    with respx.mock() as mock:
        clone = mock.post(f"{base}/voice_clone").respond(json={
            "speaker_id": "S_abc", "status": 2, "speaker_status": [{"model_type": 4, "demo_audio": "https://x.bytespeech.com/S_abc"}]})
        mock.get("https://x.bytespeech.com/S_abc").respond(content=make_wav(0.3))
        r = client.post("/api/voices/clone", data={"provider": "volcengine", "name": "火山", "voice_id": "S_abc",
                                                   "transcript": "参考", "demo_text": "试听一下",
                                                   "options": json.dumps({"language": "0", "enable_audio_denoise": True})},
                        files={"file": ("a.wav", wav, "audio/wav")})
    assert r.status_code == 200, r.text
    req = clone.calls[0].request
    assert req.headers["x-api-key"] == "volc-key-123456789"
    body = json.loads(req.content)
    assert body["speaker_id"] == "S_abc" and body["audio"]["format"] == "wav" and body["text"] == "参考"
    assert body["extra_params"] == {"demo_text": "试听一下", "enable_audio_denoise": True}
    v = r.json()
    assert v["status"] == "ready" and v["model"] == "seed-icl-2.0" and v["has_demo"]

    pcm = b"\x01\x02" * 100
    stream = "\n".join([
        json.dumps({"code": 0, "message": "", "data": base64.b64encode(pcm[:100]).decode()}),
        json.dumps({"code": 0, "message": "", "data": base64.b64encode(pcm[100:]).decode()}),
        json.dumps({"code": 20000000, "message": "OK", "data": None, "usage": {"text_words": 2}}),
    ])
    with respx.mock() as mock:
        tts = mock.post(f"{base}/unidirectional").respond(text=stream)
        r = client.post("/api/tts", json={"voice": "S_abc", "text": "你好", "format": "wav", "speed": 1.5, "pitch": 3})
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"RIFF" and r.content.endswith(pcm)
    req = tts.calls[0].request
    assert req.headers["x-api-resource-id"] == "seed-icl-2.0"
    rp = json.loads(req.content)["req_params"]
    assert rp["speaker"] == "S_abc" and rp["audio_params"]["format"] == "pcm" and rp["audio_params"]["speech_rate"] == 50
    assert json.loads(rp["additions"]) == {"post_process": {"pitch": 3}}


def test_volcengine_header_error(client):
    configure(client, "volcengine", app_id="123", access_token="tok")
    client.post("/api/voices", json={"provider": "volcengine", "voice_id": "S_x"})
    with respx.mock() as mock:
        route = mock.post("https://openspeech.bytedance.com/api/v3/tts/unidirectional").respond(
            401, json={"header": {"code": 45000010, "message": "Invalid X-Api-Key"}})
        r = client.post("/api/tts", json={"voice": "S_x", "text": "hi"})
    assert r.status_code == 400 and "45000010" in r.json()["detail"]
    h = route.calls[0].request.headers
    assert h["x-api-app-id"] == "123" and h["x-api-access-key"] == "tok"


def test_zhipu_clone_list_delete_tts(client, wav):
    configure(client, "zhipu", api_key="zp-key-123456789")
    base = "https://open.bigmodel.cn/api/paas/v4"
    with respx.mock() as mock:
        mock.post(f"{base}/files").respond(json={"id": "file-1", "object": "file"})
        clone = mock.post(f"{base}/voice/clone").respond(json={"voice": "voice_clone_1", "file_id": "demo-1"})
        mock.get(f"{base}/files/demo-1/content").respond(content=make_wav(0.2), headers={"content-type": "audio/wav"})
        r = client.post("/api/voices/clone", data={"provider": "zhipu", "name": "zhipu voice"},
                        files={"file": ("a.wav", wav, "audio/wav")})
    assert r.status_code == 200, r.text
    body = json.loads(clone.calls[0].request.content)
    assert body["model"] == "glm-tts-clone" and body["file_id"] == "file-1" and body["input"]
    v = r.json()
    assert v["voice_id"] == "voice_clone_1" and v["has_demo"]

    with respx.mock() as mock:
        speech = mock.post(f"{base}/audio/speech").respond(content=make_wav(0.4), headers={"content-type": "audio/wav"})
        r = client.post("/api/tts", json={"voice": v["id"], "text": "你好", "format": "mp3"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    body = json.loads(speech.calls[0].request.content)
    assert body["response_format"] == "wav" and body["voice"] == "voice_clone_1"

    with respx.mock() as mock:
        mock.get(f"{base}/voice/list").respond(json={"voice_list": [
            {"voice": "voice_clone_1", "voice_name": "a", "voice_type": "PRIVATE"},
            {"voice": "voice_clone_2", "voice_name": "b", "voice_type": "PRIVATE", "download_url": "https://x/b.mp3"},
        ]})
        r = client.post("/api/providers/zhipu/sync")
    assert r.json() == {"added": 1, "updated": 1, "total": 2}

    with respx.mock() as mock:
        delete = mock.post(f"{base}/voice/delete").respond(json={"voice": "voice_clone_1"})
        r = client.delete(f"/api/voices/{v['id']}?remote=true")
    assert r.status_code == 200 and delete.called
    assert client.get(f"/api/voices/{v['id']}").status_code == 404
