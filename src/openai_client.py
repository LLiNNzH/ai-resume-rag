from __future__ import annotations

from typing import Any, Dict, List

from openai import OpenAI

from src.settings import SETTINGS


class _NoOpClient:
    pass


def build_client():
    """Return an OpenAI client if API key exists; otherwise return None.

    Offline mode is handled in src.match / src.serve.
    """
    if not SETTINGS.api_key.strip():
        return None
    return OpenAI(
        base_url=SETTINGS.base_url,
        api_key=SETTINGS.api_key,
    )
