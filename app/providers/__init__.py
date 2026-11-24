"""Provider registry."""
from __future__ import annotations

from .aliyun import AliyunProvider
from .base import BaseProvider, CloneRequest, CloneResult, ProviderError, RemoteVoice, SynthesisResult
from .minimax import MinimaxProvider
from .volcengine import VolcengineProvider
from .zhipu import ZhipuProvider

PROVIDERS: dict[str, type[BaseProvider]] = {
    cls.name: cls for cls in (VolcengineProvider, AliyunProvider, MinimaxProvider, ZhipuProvider)
}


def get_provider_cls(name: str) -> type[BaseProvider]:
    try:
        return PROVIDERS[name]
    except KeyError:
        raise ProviderError(f"未知的平台: {name}", status_code=404) from None


__all__ = [
    "PROVIDERS",
    "BaseProvider",
    "CloneRequest",
    "CloneResult",
    "ProviderError",
    "RemoteVoice",
    "SynthesisResult",
    "get_provider_cls",
]
