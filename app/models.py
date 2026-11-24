"""ORM models."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProviderConfig(Base):
    __tablename__ = "provider_configs"

    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Voice(Base):
    __tablename__ = "voices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    voice_id: Mapped[str] = mapped_column(String(256), index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    # ready | training | failed | unknown
    status: Mapped[str] = mapped_column(String(16), default="unknown")
    status_message: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    language: Mapped[str] = mapped_column(String(32), default="")
    # clone | import | manual
    source: Mapped[str] = mapped_column(String(16), default="manual")
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    sample_path: Mapped[str] = mapped_column(String(512), default="")
    sample_text: Mapped[str] = mapped_column(Text, default="")
    demo_path: Mapped[str] = mapped_column(String(512), default="")
    demo_url: Mapped[str] = mapped_column(Text, default="")
    default_params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Generation(Base):
    __tablename__ = "generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    voice_pk: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("voices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), index=True)
    voice_id: Mapped[str] = mapped_column(String(256))
    voice_name: Mapped[str] = mapped_column(String(128), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    text: Mapped[str] = mapped_column(Text)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    audio_path: Mapped[str] = mapped_column(String(512), default="")
    audio_format: Mapped[str] = mapped_column(String(16), default="mp3")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    # web | api | openai
    source: Mapped[str] = mapped_column(String(16), default="web")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    prefix: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
