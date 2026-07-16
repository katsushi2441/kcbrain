from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    host: str
    port: int
    api_token: str
    allowed_client_ips: frozenset[str]
    ollama_url: str
    ollama_model: str
    ollama_timeout: int
    max_input_chars: int


def load_settings() -> Settings:
    allowed = {
        value.strip()
        for value in os.getenv("KCBRAIN_ALLOWED_CLIENT_IPS", "127.0.0.1,::1,157.7.188.210").split(",")
        if value.strip()
    }
    return Settings(
        host=os.getenv("KCBRAIN_HOST", "0.0.0.0"),
        port=int(os.getenv("KCBRAIN_PORT", "18328")),
        api_token=os.getenv("KCBRAIN_API_TOKEN", "").strip(),
        allowed_client_ips=frozenset(allowed),
        ollama_url=os.getenv("KCBRAIN_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
        ollama_model=os.getenv("KCBRAIN_OLLAMA_MODEL", "gemma4:12b-it-qat").strip(),
        ollama_timeout=int(os.getenv("KCBRAIN_OLLAMA_TIMEOUT", "600")),
        max_input_chars=int(os.getenv("KCBRAIN_MAX_INPUT_CHARS", "80000")),
    )


settings = load_settings()
