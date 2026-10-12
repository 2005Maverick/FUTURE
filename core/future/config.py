"""Configuration loaded from the repo-root .env (never committed)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")


@dataclass(frozen=True)
class Config:
    supabase_url: str | None
    supabase_secret_key: str | None
    supabase_publishable_key: str | None
    openalex_api_key: str | None
    exa_api_key: str | None
    kaggle_api_token: str | None

    @property
    def has_db_write_access(self) -> bool:
        return bool(self.supabase_url and self.supabase_secret_key)


def load() -> Config:
    get = os.environ.get
    return Config(
        supabase_url=get("SUPABASE_URL"),
        supabase_secret_key=get("SUPABASE_SECRET_KEY") or None,
        supabase_publishable_key=get("SUPABASE_PUBLISHABLE_KEY"),
        openalex_api_key=get("OPENALEX_API_KEY"),
        exa_api_key=get("EXA_API_KEY"),
        kaggle_api_token=get("KAGGLE_API_TOKEN"),
    )
