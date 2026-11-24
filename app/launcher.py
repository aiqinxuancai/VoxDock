"""Desktop launcher — used by ``python -m app`` and the packaged Windows ``VoxDock.exe``.

* Portable: ``.env`` and ``data/`` live next to the executable (falls back to %LOCALAPPDATA%\\VoxDock
  when that folder is not writable, e.g. under Program Files).
* Binds to 127.0.0.1 by default (set ``VOXDOCK_HOST=0.0.0.0`` for LAN access).
* Opens the browser once the server is ready (disable with ``VOXDOCK_NO_BROWSER=1``).
* If VoxDock is already running on the port it just opens the browser; if the port is taken by
  something else it picks the next free port.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _is_voxdock(host: str, port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/healthz", timeout=1.5) as resp:
            return b'"ok"' in resp.read()
    except Exception:  # noqa: BLE001
        return False


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def _open_when_ready(url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/healthz", timeout=1):
                webbrowser.open(url)
                return
        except Exception:  # noqa: BLE001
            time.sleep(0.4)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def main() -> None:
    base = base_dir()
    os.chdir(base)  # .env / data are resolved relative to the app folder
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass

    from .config import APP_VERSION, get_settings  # importing loads .env into os.environ

    if not os.environ.get("VOXDOCK_DATA_DIR"):
        data = base / "data"
        if not _writable(data):
            data = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "VoxDock" / "data"
        os.environ["VOXDOCK_DATA_DIR"] = str(data)
    get_settings.cache_clear()
    settings = get_settings()
    host = os.environ.get("VOXDOCK_HOST", "127.0.0.1")
    port = settings.port
    browse_host = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    open_browser = not _truthy(os.environ.get("VOXDOCK_NO_BROWSER"))

    if _is_voxdock(browse_host, port):
        url = f"http://{browse_host}:{port}"
        print(f"VoxDock 已在运行：{url}")
        if open_browser:
            webbrowser.open(url)
        return
    if not _port_free(host, port):
        for candidate in range(port + 1, port + 100):
            if _port_free(host, candidate):
                print(f"端口 {port} 已被占用，改用 {candidate}")
                port = candidate
                break
    url = f"http://{browse_host}:{port}"

    line = "=" * 56
    print(line)
    print(f"  VoxDock v{APP_VERSION}  多平台声音克隆聚合平台")
    print(f"  访问地址: {url}")
    if host in ("0.0.0.0", "::"):
        print("  已开启局域网访问，请使用本机 IP 访问")
    print(f"  数据目录: {settings.data_dir.resolve()}")
    if not settings.admin_password:
        print("  提示: 未设置管理员密码 (VOXDOCK_ADMIN_PASSWORD)，仅建议本机使用")
    print("  关闭此窗口或按 Ctrl+C 即可退出")
    print(line, flush=True)

    if open_browser:
        threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()

    import uvicorn

    from .main import app

    uvicorn.run(app, host=host, port=port, log_level=os.environ.get("VOXDOCK_LOG_LEVEL", "info"))


def run() -> None:
    """Entry point that keeps the console open on fatal errors (double-click friendly)."""
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        if getattr(sys, "frozen", False):
            try:
                input("\n启动失败，按回车键退出...")
            except EOFError:
                pass
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    run()
