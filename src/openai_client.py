from __future__ import annotations

from openai import OpenAI

from src.settings import SETTINGS


def build_client():
    # 使用 OpenAI 兼容协议：OpenAI(base_url=..., api_key=...)
    # provider 暂时不做分支（只要兼容即可）
    return OpenAI(
        base_url=SETTINGS.base_url,
        api_key=SETTINGS.api_key or "",
    )
