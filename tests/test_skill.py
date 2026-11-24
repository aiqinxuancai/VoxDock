"""Keep skills/voxdock-api (API guide + CLI) in sync with the API, and exercise its CLI."""
import importlib.util
import io
import json
import re
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit

import pytest
import respx

from .conftest import configure, make_wav

SKILL = Path(__file__).resolve().parent.parent / "skills" / "voxdock-api"
# table rows: | `GET` | `/api/x` |   and headings:  ### `POST /api/tts`
ROUTE_RE = re.compile(r"`(GET|POST|PUT|PATCH|DELETE)(?:`\s*\|\s*`| )(/[^`?\s]*)")


def _frontmatter(text: str) -> dict:
    assert text.startswith("---\n"), "SKILL.md must start with YAML frontmatter"
    block = text.split("---\n", 2)[1]
    return dict(line.split(": ", 1) for line in block.strip().splitlines())


def test_skill_frontmatter():
    meta = _frontmatter((SKILL / "SKILL.md").read_text(encoding="utf-8"))
    assert meta["name"] == "voxdock-api" and re.fullmatch(r"[a-z0-9-]{1,64}", meta["name"])
    assert 0 < len(meta["description"]) <= 1024
    body = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    for link in re.findall(r"\]\(((?:reference|scripts)/[^)]+)\)", body):
        assert (SKILL / link).is_file(), link


def _norm(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path)


def test_documented_endpoints_match_routes():
    from app.main import app

    routes = {("GET", "/healthz")}  # excluded from the OpenAPI schema on purpose
    for path, ops in app.openapi()["paths"].items():
        routes |= {(m.upper(), _norm(path)) for m in ops if m in ("get", "post", "put", "patch", "delete")}
    assert len(routes) > 20
    documented = {(m, _norm(p)) for m, p in ROUTE_RE.findall((SKILL / "reference" / "endpoints.md").read_text(encoding="utf-8"))}
    assert routes - documented == set(), "routes missing from reference/endpoints.md"
    assert documented - routes == set(), "reference/endpoints.md documents routes that do not exist"


def test_provider_reference_covers_params():
    from app.providers import PROVIDERS

    text = (SKILL / "reference" / "providers.md").read_text(encoding="utf-8")
    sections = dict(re.findall(r"^## \S+.*?`(\w+)`\n(.*?)(?=^## |\Z)", text, flags=re.M | re.S))
    for name, cls in PROVIDERS.items():
        assert name in sections, f"providers.md has no section for {name}"
        sec = sections[name]
        for f in [*cls.tts_params, *cls.clone_fields]:
            assert f"`{f.key}`" in sec, f"{name}: `{f.key}` not documented"
        for m in cls.models:
            assert f"`{m['value']}`" in sec, f"{name}: model {m['value']} not documented"


# ------------------------------------------------------------------ CLI
@pytest.fixture()
def cli(client, monkeypatch):
    spec = importlib.util.spec_from_file_location("voxdock_cli", SKILL / "scripts" / "voxdock.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    class Resp:
        def __init__(self, r):
            self._r, self.headers = r, r.headers

        def read(self):
            return self._r.content

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout=None):
        u = urlsplit(req.full_url)
        r = client.request(req.get_method(), u.path + (f"?{u.query}" if u.query else ""),
                           content=req.data, headers=dict(req.header_items()))
        if r.status_code >= 400:
            raise HTTPError(req.full_url, r.status_code, r.reason_phrase, r.headers, io.BytesIO(r.content))
        return Resp(r)

    monkeypatch.setattr(mod, "urlopen", fake_urlopen)
    monkeypatch.delenv("VOXDOCK_API_KEY", raising=False)
    return lambda *args: mod.main(["--url", "http://testserver", *args])


def test_cli_workflow(cli, client, capsys, tmp_path):
    configure(client, "minimax", api_key="mm-key-123456789")
    assert cli("health") == 0
    assert "minimax" in capsys.readouterr().out

    a, b = tmp_path / "第一段.wav", tmp_path / "b.wav"
    a.write_bytes(make_wav(1.0))
    b.write_bytes(make_wav(1.5))
    with respx.mock() as mock:
        mock.post("https://api.minimax.cn/v1/files/upload").respond(json={"file": {"file_id": 1}, "base_resp": {"status_code": 0}})
        mock.post("https://api.minimax.cn/v1/voice_clone").respond(json={"base_resp": {"status_code": 0}})
        assert cli("clone", "--provider", "minimax", "--name", "多段", str(a), str(b),
                   "--option", "need_noise_reduction=true", "--tags", "女声,测试", "--json") == 0
    out = capsys.readouterr().out
    voice = json.loads(out[out.index("{"):])
    assert voice["extra"]["merged"] is True and voice["extra"]["reference_count"] == 2
    assert voice["extra"]["options"] == {"need_noise_reduction": True} and voice["tags"] == ["女声", "测试"]

    hex_audio = make_wav(0.2).hex()
    with respx.mock() as mock:
        t2a = mock.post("https://api.minimax.cn/v1/t2a_v2").respond(
            json={"data": {"audio": hex_audio}, "extra_info": {"audio_length": 200}, "base_resp": {"status_code": 0}})
        assert cli("tts", "多段", "你好", "-o", str(tmp_path / "out.mp3"), "--speed", "1.2",
                   "--format", "wav", "--param", "emotion=happy") == 0
    sent = json.loads(t2a.calls[0].request.content)
    assert sent["voice_setting"]["speed"] == 1.2 and sent["voice_setting"]["emotion"] == "happy"
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert result["generation_id"] and result["format"] == "wav" and Path(result["file"]).name == "out.wav"
    assert Path(result["file"]).read_bytes()[:4] == b"RIFF"

    assert cli("voices", "--status", "ready") == 0 and "多段" in capsys.readouterr().out
    assert cli("history") == 0 and "你好" in capsys.readouterr().out
    assert cli("update", str(voice["id"]), "--default-param", "speed=1.1", "--favorite", "true") == 0
    assert client.get(f"/api/voices/{voice['id']}").json()["default_params"] == {"speed": 1.1}
    capsys.readouterr()

    assert cli("tts", "nobody", "hi") == 1
    assert "HTTP 404" in capsys.readouterr().err
    assert cli("delete", str(voice["id"])) == 0
    assert client.get("/api/voices").json()["items"] == []


def test_cli_requires_key_when_auth_enabled(cli, client, capsys, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("VOXDOCK_ADMIN_PASSWORD", "pw")
    monkeypatch.setenv("VOXDOCK_API_KEYS", "vd-static-key")
    get_settings.cache_clear()
    assert cli("voices") == 1
    assert "VOXDOCK_API_KEY" in capsys.readouterr().err
    assert cli("--key", "vd-static-key", "voices") == 0
