"""Operator settings and explicit local credential loading."""

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

KEY_NAMES = {
    "OpenAI": "OPENAI_API_KEY",
    "Anthropic": "ANTHROPIC_API_KEY",
    "Gemini": "GEMINI_API_KEY",
}


@dataclass(frozen=True)
class Settings:
    mode: str
    database: Path
    dotenv: Path | None
    ollama_url: str | None

    @property
    def local(self) -> bool:
        return self.mode == "local"


def settings() -> Settings:
    mode = os.getenv("RADAR_MODE", "local")
    if mode not in {"local", "hosted"}:
        raise ValueError("RADAR_MODE must be local or hosted.")
    dotenv_path = os.getenv("RADAR_DOTENV") if mode == "local" else None
    ollama_url = (
        os.getenv("RADAR_OLLAMA_URL", "http://127.0.0.1:11434") if mode == "local" else None
    )
    return Settings(
        mode,
        Path(os.getenv("RADAR_DB", str(Path.home() / ".data-ai-radar" / "history.sqlite3"))),
        Path(dotenv_path) if dotenv_path else None,
        validate_ollama(ollama_url) if ollama_url else None,
    )


def validate_ollama(value: str) -> str:
    parsed = urlsplit(value)
    port = parsed.port
    allowed_hosts = {"localhost", "127.0.0.1", "::1", "host.docker.internal", "ollama"}
    if (
        port == 0
        or parsed.scheme not in {"http", "https"}
        or parsed.hostname not in allowed_hosts
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "RADAR_OLLAMA_URL must point to loopback or the documented Docker host/service."
        )
    return value.rstrip("/")


def local_key(config: Settings, provider: str, path: Path | None = None) -> str | None:
    chosen_path = path or config.dotenv
    if not config.local or chosen_path is None or provider not in KEY_NAMES:
        return None
    if not chosen_path.is_file():
        raise ValueError("The configured local credential file does not exist.")
    value = dotenv_values(chosen_path, interpolate=False).get(KEY_NAMES[provider])
    return value.strip() if value else None
