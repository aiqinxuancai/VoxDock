import os
import struct

import pytest


def make_wav(seconds: float = 1.0, sr: int = 24000) -> bytes:
    n = int(seconds * sr)
    pcm = b"\x00\x10" * n
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE" + b"fmt "
            + struct.pack("<IHHIIHH", 16, 1, 1, sr, sr * 2, 2, 16) + b"data" + struct.pack("<I", len(pcm)) + pcm)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("VOXDOCK_DATA_DIR", str(tmp_path))
    for key in ("VOXDOCK_ADMIN_PASSWORD", "VOXDOCK_API_KEYS", "MINIMAX_API_KEY", "DASHSCOPE_API_KEY",
                "ZHIPU_API_KEY", "VOLC_API_KEY", "VOLC_APP_ID", "VOLC_ACCESS_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


@pytest.fixture()
def wav() -> bytes:
    return make_wav(2.0)


def configure(client, provider: str, **values):
    r = client.put(f"/api/providers/{provider}/config", json={"values": values})
    assert r.status_code == 200, r.text
    return r.json()


os.environ.setdefault("PYTHONIOENCODING", "utf-8")
