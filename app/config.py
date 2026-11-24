"""Application settings (environment variables, prefix ``VOXDOCK_``)."""
from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_dotenv(path: str = ".env") -> None:
    """Load KEY=VALUE pairs from .env into os.environ (provider keys like DASHSCOPE_API_KEY)."""
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip().removeprefix("export ").strip(), val.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, val)


_load_dotenv()



def _version() -> str:
    if os.environ.get("VOXDOCK_VERSION"):
        return os.environ["VOXDOCK_VERSION"].lstrip("v")
    try:  # written by the release pipeline (Windows build)
        from ._version import __version__

        return __version__
    except ImportError:
        return "1.0.0"


APP_NAME = "VoxDock"
APP_VERSION = _version()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VOXDOCK_",
        env_file=".env",
        env_file_encoding="utf-8-sig",
        extra="ignore",
    )

    data_dir: Path = Field(default=Path("data"), description="数据目录（数据库、音频文件）")
    host: str = "0.0.0.0"
    port: int = 8000

    # Web 管理后台密码；为空时不启用登录（仅建议本地使用）
    admin_password: str = ""
    # 会话签名密钥；为空时自动生成并保存在数据目录
    secret_key: str = ""
    # 额外的静态 API Key（逗号分隔），可与后台创建的 Key 同时使用
    api_keys: str = ""
    # 会话有效期（天）
    session_days: int = 30

    # 调用各平台的超时时间（秒）
    request_timeout: float = 120.0
    # 上传参考音频大小上限（MB，单个文件）
    max_upload_mb: int = 20
    # 单次复刻最多上传的参考音频段数
    max_reference_audios: int = 10
    # 平台只支持单条参考音频时，多段音频本地合并的间隔（秒）
    merge_gap_seconds: float = 2.0
    # 单次合成文本长度上限
    max_text_length: int = 10000

    @property
    def db_path(self) -> Path:
        return self.data_dir / "voxdock.db"

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    def static_api_keys(self) -> set[str]:
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}

    def ensure_dirs(self) -> None:
        for sub in ("", "audio", "audio/generations", "audio/samples", "audio/demos"):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)

    def resolved_secret(self) -> str:
        if self.secret_key:
            return self.secret_key
        path = self.data_dir / ".secret_key"
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        key = secrets.token_urlsafe(48)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(key, encoding="utf-8")
        return key


@lru_cache
def get_settings() -> Settings:
    return Settings()
