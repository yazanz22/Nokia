"""Runtime configuration, loaded from environment / .env.

See .env.example at the repo root for the full list with descriptions.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = .../Nokia  (this file is .../Nokia/backend/app/config.py)
REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = REPO_ROOT / "data" / "dataset1.csv"
HISTORY_PATH = REPO_ROOT / "data" / "telemetry_history.csv"
MODEL_PATH = REPO_ROOT / "ml" / "model.pkl"
FORECAST_MODEL_PATH = REPO_ROOT / "ml" / "forecast_model.pkl"
COMPONENT_MODEL_PATH = REPO_ROOT / "ml" / "component_model.pkl"


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
    # Verified on the Groq free tier. llama-3.3-70b is NOT available on our key,
    # so it must not be the default — a deploy without .env would 404 on every call.
    llm_model: str = "groq:openai/gpt-oss-120b"
    # Groq's free tier allows 8,000 tokens/minute and one investigation costs on the
    # order of a thousand. Running several at once self-inflicts a 429 and silently
    # drops the whole demo to the rule agent, so investigations queue instead.
    agent_max_concurrent: int = 1
    groq_api_key: str = ""
    gemini_api_key: str = ""

    # ── App ─────────────────────────────────────────────────────────────────
    # The absolute URL this deployment answers on, e.g.
    # https://filo-asset-sentinel.onrender.com. Configured, never inferred: the only
    # thing we hand out is the CAMARA geofencing callback sink, and a sink is a URL
    # the *operator* will POST to on our credentials. Deriving it from the request
    # would derive it from the Host header, which the caller writes — so anyone who
    # can reach this public demo could aim a subscription made on our Nokia account
    # at a server of their choosing. Unset means no subscription is registered
    # (see routes/debug.py); it must never quietly fall back to the request.
    public_base_url: str = ""
    # 0.0.0.0 in a container; hosts inject the port via $PORT.
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    sim_tick_seconds: float = 2.0
    silent_threshold_seconds: int = 30
    demo_fleet_size: int = 30
    # A real repair takes the work order's ETA. Nothing would ever complete inside a
    # demo at that rate, so dispatched jobs finish after this many seconds of wall
    # clock instead — the technician returns to the pool and the machine comes back
    # online. Without it the six technicians are permanently busy after six dispatches
    # and every later work order is raised with nobody assigned.
    work_order_complete_seconds: int = 90
    # A blind spot is closed with "no dispatch — we'll re-check automatically", and an
    # ops team would re-check in about fifteen minutes. Nobody watching a demo will wait
    # that long, so the nominal interval is compressed to this many seconds of wall
    # clock (see agent/tools.py::RECHECK_NOMINAL_MINUTES). The trace prints whatever
    # this produces, so the promise on screen is always the promise that gets kept.
    recheck_after_seconds: int = 45
    # "Now" for the predictive-maintenance view: telemetry history is replayed up to
    # this instant, so the fleet shows a mix of healthy and mid-degradation machines
    # rather than only ones that have already died.
    forecast_as_of: str = "2026-08-18T06:00:00"
    # /docs, /redoc and /openapi.json. On by default: the generated reference is how a
    # judge inspects the CAMARA surface without reading the source — the live-check
    # endpoint, the geofencing sink, the scenario controls — and it exposes no secret,
    # because it describes routes that answer to plain curl either way. What Swagger's
    # "Try it out" adds is convenience, not access: every mutating route here is
    # deliberately unauthenticated (scenario injection is already rate-limited, and
    # reset is a button on the dashboard itself), so the exposure is those routes, not
    # their documentation, and hiding the documentation would cost the demo its
    # clearest self-explanation while moving nothing. It is a switch rather than a
    # constant because that calculus changes the day this URL outlives the hackathon.
    docs_enabled: bool = True
    # How many dashboards the event bus will carry at once. The deployed demo is a
    # single public URL with no authentication, so the number of listeners is whatever
    # the internet decides. Each one costs a 1000-slot queue, a full store.snapshot()
    # at connect time, and a slot in every fan-out for the life of the socket — on a
    # 512MB instance a shared link, a crawler or a reconnect storm holding sockets open
    # is enough to walk the process into the OOM killer. Past this many the bus refuses
    # outright rather than degrading for the people already watching; the dashboard
    # reconnects with backoff, so a refusal is temporary from the client's side.
    max_ws_subscribers: int = 32

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

    def public_url(self, path: str) -> str | None:
        """An absolute URL on this deployment for ``path``, or None if unavailable.

        Returns None when PUBLIC_BASE_URL is unset or is not an absolute http(s)
        URL — callers must treat that as "we have no public address" and skip
        whatever they were going to hand out. Validated here rather than at the call
        site so there is exactly one place that decides what we are willing to send
        to an operator.
        """
        base = self.public_base_url.strip()
        if not base or any(ch.isspace() for ch in base):
            return None
        try:
            parsed = urlparse(base)
        except ValueError:
            return None
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None
        # Rebuild from the parsed parts rather than concatenating the raw string:
        # anything the parser did not recognise as scheme/host/path is dropped
        # instead of being forwarded.
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}{path}"

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
