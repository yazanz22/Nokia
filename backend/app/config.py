"""Runtime configuration, loaded from environment / .env.

See .env.example at the repo root for the full list with descriptions.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = .../Nokia  (this file is .../Nokia/backend/app/config.py)
REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = REPO_ROOT / "data" / "dataset1.csv"
HISTORY_PATH = REPO_ROOT / "data" / "telemetry_history.csv"
MODEL_PATH = REPO_ROOT / "ml" / "model.pkl"
FORECAST_MODEL_PATH = REPO_ROOT / "ml" / "forecast_model.pkl"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Nokia Network as Code ────────────────────────────────────────────────
    nac_mode: str = "mock"  # "mock" | "live"
    nac_api_key: str = ""
    nac_device_map: str = ""  # "EQ-0007:+3197...,EQ-0042:+3197..."
    # Verified sandbox transport (see app/nac/nokia.py). RapidAPI-style auth.
    nac_api_host: str = "network-as-code.p-eu.apihub.nokia.io"
    nac_rapidapi_host: str = "network-as-code.nokia.rapidapi.com"
    # The sandbox issues far fewer test MSISDNs than we have assets; unmapped
    # assets fall back to this one so every call stays genuinely live.
    nac_default_device: str = "+99999991000"
    nac_timeout_seconds: float = 20.0

    # ── AI agent layer ──────────────────────────────────────────────────────
    agent_mode: str = "rule"  # "rule" | "llm"
    llm_model: str = "groq:llama-3.3-70b-versatile"
    groq_api_key: str = ""
    gemini_api_key: str = ""

    # ── App ─────────────────────────────────────────────────────────────────
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    sim_tick_seconds: float = 2.0
    silent_threshold_seconds: int = 30
    demo_fleet_size: int = 30
    # "Now" for the predictive-maintenance view: telemetry history is replayed up to
    # this instant, so the fleet shows a mix of healthy and mid-degradation machines
    # rather than only ones that have already died.
    forecast_as_of: str = "2026-08-18T06:00:00"

    def export_provider_keys(self) -> None:
        """Publish LLM keys into the process environment.

        Pydantic AI providers read their credentials from environment variables, but
        ours live in .env and are loaded into this settings object — so without this
        the agent raises "set the GROQ_API_KEY environment variable" and silently
        falls back to the rule agent. Done here rather than per-provider so
        LLM_MODEL stays swappable.
        """
        for var, value in (
            ("GROQ_API_KEY", self.groq_api_key),
            ("GEMINI_API_KEY", self.gemini_api_key),
            ("GOOGLE_API_KEY", self.gemini_api_key),
        ):
            if value and not os.environ.get(var):
                os.environ[var] = value

    def device_map(self) -> dict[str, str]:
        """Parse NAC_DEVICE_MAP into {asset_id: phone_number}."""
        out: dict[str, str] = {}
        for pair in self.nac_device_map.split(","):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            asset_id, phone = pair.split(":", 1)
            out[asset_id.strip()] = phone.strip()
        return out


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.export_provider_keys()
    return settings
