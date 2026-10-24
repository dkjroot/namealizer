"""Chat-only configuration, adapted from IRIS (GPL-3.0-only)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

CONFIG = Path("local-config.json")


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    base_url: str = "http://127.0.0.1:5001/v1"
    model: str = "local-model"
    api_key: SecretStr | None = Field(default=None, exclude=True)
    allow_remote: bool = False
    system_prompt: str = "You suggest memorable project names. Follow the requested JSON format."
    temperature: float = Field(default=0.8, ge=0, le=2)
    max_tokens: int = Field(default=2400, gt=0, le=32768)
    timeout: float = Field(default=120, gt=0, le=600)
    history_turns: int = Field(default=0, ge=0, le=100)
    trace: bool = False
    reply_encoding: str = "text"

    @field_validator("base_url")
    @classmethod
    def endpoint(cls, value: str) -> str:
        parts = urlsplit(value)
        _ = parts.port
        if (parts.scheme not in {"http", "https"} or not parts.hostname
                or parts.username or parts.password or parts.query or parts.fragment):
            raise ValueError("Use an http(s) base URL without credentials, query or fragment")
        return value.rstrip("/")

    @field_validator("model")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Model must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def privacy(self) -> Settings:
        parts = urlsplit(self.base_url)
        if parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
            if not self.allow_remote or parts.scheme != "https":
                raise ValueError("Remote endpoints require HTTPS and explicit allow_remote=true")
        if self.trace or self.history_turns or self.reply_encoding != "text":
            raise ValueError("Use trace=false, history_turns=0 and reply_encoding=text")
        return self


def load_settings(profile: str, path: Path = CONFIG) -> Settings:
    data = json.loads(path.read_text(encoding="utf-8"))
    if profile not in data:
        raise ValueError(f"No {profile} profile. Run with --configure first.")
    return Settings.model_validate({**data[profile], "api_key": os.getenv("NAMEALIZER_API_KEY")})


def configure(path: Path = CONFIG) -> None:
    profiles = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for profile in ("local", "remote"):
        previous = profiles.get(profile, {})
        default = previous.get("base_url", "http://127.0.0.1:5001/v1" if profile == "local" else "")
        url = input(f"{profile.title()} chat base URL [{default or 'skip'}]: ").strip() or default
        if not url:
            continue
        model = input(f"Model [{previous.get('model', 'local-model')}]: ").strip()
        if profile == "remote":
            print(f"Project descriptions, keywords and favourites will be sent to {url}.")
            if input("Allow this endpoint? [y/N]: ").strip().lower() != "y":
                continue
        settings = Settings(base_url=url, model=model or previous.get("model", "local-model"),
                            allow_remote=profile == "remote")
        profiles[profile] = settings.model_dump(mode="json")
    path.write_text(json.dumps(profiles, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Saved {path}. Keys belong in NAMEALIZER_API_KEY, not this file.")
