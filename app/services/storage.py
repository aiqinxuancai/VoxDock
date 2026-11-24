"""Local file storage for audio (paths stored relative to the data dir)."""
from __future__ import annotations

import uuid
from pathlib import Path

from ..audio import ext_for
from ..config import get_settings


def abs_path(rel: str) -> Path:
    return get_settings().data_dir / rel


def save(kind: str, data: bytes, fmt: str) -> str:
    """Save bytes under audio/<kind>/ and return the relative path."""
    rel = f"audio/{kind}/{uuid.uuid4().hex}.{ext_for(fmt)}"
    path = abs_path(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return rel


def remove(rel: str | None) -> None:
    if not rel:
        return
    path = abs_path(rel)
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def exists(rel: str | None) -> bool:
    return bool(rel) and abs_path(rel).is_file()
