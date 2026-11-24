"""Core API behaviour: config masking, voice resolution, auth, OpenAI compat."""
import respx

from app.audio import detect_format, mp3_duration_ms, pcm_to_wav, wav_duration_ms

from .conftest import configure, make_wav


def test_providers_meta(client):
    items = client.get("/api/providers").json()["items"]
    assert [p["name"] for p in items] == ["volcengine", "aliyun", "minimax", "zhipu"]
    for p in items:
        assert p["tts_params"] and p["models"] and not p["configured"]


def test_config_masking_and_env(client, monkeypatch):
    cfg = configure(client, "aliyun", api_key="sk-abcdefghijk1234")
    assert cfg["values"]["api_key"] == "sk-••••1234" and cfg["configured"]
    # masked value posted back keeps the secret unchanged
    cfg = configure(client, "aliyun", api_key="sk-••••1234")
    assert cfg["values"]["api_key"] == "sk-••••1234"
    # clearing falls back to env var
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-from-env-99999")
    cfg = configure(client, "aliyun", api_key="")
    assert cfg["sources"]["api_key"] == "env" and cfg["values"]["api_key"].endswith("9999")


def test_unconfigured_provider_error(client):
    r = client.post("/api/tts", json={"voice": "zhipu:tongtong", "text": "hi"})
    assert r.status_code == 400 and "尚未配置" in r.json()["detail"]


def test_voice_resolution_and_openai(client):
    configure(client, "zhipu", api_key="zp-key-123456789")
    v = client.post("/api/voices", json={"provider": "zhipu", "voice_id": "tongtong", "name": "彤彤"}).json()
    assert client.post("/api/voices", json={"provider": "zhipu", "voice_id": "tongtong"}).status_code == 409
    with respx.mock() as mock:
        mock.post("https://open.bigmodel.cn/api/paas/v4/audio/speech").respond(content=make_wav(0.1), headers={"content-type": "audio/wav"})
        for ref in (v["id"], str(v["id"]), "tongtong", "彤彤", "zhipu:tongtong"):
            r = client.post("/api/tts", json={"voice": ref, "text": "hi", "save": False})
            assert r.status_code == 200, (ref, r.text)
        r = client.post("/api/tts", json={"voice": "zhipu:chuichui", "text": "ad-hoc"})
        assert r.status_code == 200 and r.headers["x-voice-id"] == "chuichui"
        r = client.post("/v1/audio/speech", json={"model": "tts-1", "voice": "彤彤", "input": "openai", "response_format": "mp3"})
        assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
        r = client.get("/api/tts", params={"voice": "tongtong", "text": "get"})
        assert r.status_code == 200 and r.headers.get("x-generation-id")
    assert client.post("/api/tts", json={"voice": "nobody", "text": "hi"}).status_code == 404
    gens = client.get("/api/generations").json()
    assert gens["total"] == 3
    assert {g["source"] for g in gens["items"]} == {"api", "openai"}
    v2 = client.get(f"/api/voices/{v['id']}").json()
    assert v2["usage_count"] == 7


def test_text_limits(client):
    configure(client, "zhipu", api_key="zp-key-123456789")
    client.post("/api/voices", json={"provider": "zhipu", "voice_id": "tongtong"})
    r = client.post("/api/tts", json={"voice": "tongtong", "text": "长" * 1100})
    assert r.status_code == 400 and "1024" in r.json()["detail"]
    assert client.post("/api/tts", json={"voice": "tongtong", "text": "   "}).status_code == 400


def test_auth_flow(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("VOXDOCK_ADMIN_PASSWORD", "s3cret")
    get_settings.cache_clear()
    assert client.get("/api/voices").status_code == 401
    assert client.get("/api/auth/status").json() == {"auth_enabled": True, "authenticated": False, "identity": None}
    assert client.post("/api/auth/login", json={"password": "bad"}).status_code == 401
    assert client.post("/api/auth/login", json={"password": "s3cret"}).status_code == 200
    assert client.get("/api/voices").status_code == 200
    key = client.post("/api/keys", json={"name": "ci"}).json()["key"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert client.get("/api/voices").status_code == 401
    assert client.get("/api/voices", headers={"Authorization": f"Bearer {key}"}).status_code == 200
    assert client.get("/api/voices", headers={"X-API-Key": key}).status_code == 200
    assert client.get(f"/api/voices?api_key={key}").status_code == 200
    # API keys cannot manage credentials or keys
    assert client.get("/api/keys", headers={"Authorization": f"Bearer {key}"}).status_code == 403
    assert client.put("/api/providers/zhipu/config", json={"values": {}}, headers={"Authorization": f"Bearer {key}"}).status_code == 403
    monkeypatch.setenv("VOXDOCK_API_KEYS", "static-key-1")
    get_settings.cache_clear()
    assert client.get("/api/voices", headers={"Authorization": "Bearer static-key-1"}).status_code == 200


def test_audio_helpers():
    wav = make_wav(1.5)
    assert detect_format(wav) == "wav" and wav_duration_ms(wav) == 1500
    assert wav_duration_ms(pcm_to_wav(b"\x00\x00" * 24000)) == 1000
    frame = bytes([0xFF, 0xFB, 0x90, 0x00]) + b"\x00" * 15996  # MPEG1 L3 128kbps
    assert detect_format(frame) == "mp3" and mp3_duration_ms(frame) == 1000
    assert detect_format(b"OggS" + b"\x00" * 20) == "ogg"
    assert detect_format(b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 20) == "m4a"
    assert detect_format(b"garbage-bytes", "x.flac") == "flac"


def test_spa_and_static(client):
    assert "VoxDock" in client.get("/").text
    assert client.get("/static/js/main.js").status_code == 200
    assert client.get("/healthz").json()["status"] == "ok"
    assert client.get("/api/does-not-exist").status_code == 404
