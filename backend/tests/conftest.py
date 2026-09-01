import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.simulator import simulator  # noqa: E402
from app.store import store  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def deterministic_agent():
    """Pin the suite to the rule agent.

    .env may set AGENT_MODE=llm for the demo. Tests must not depend on a network
    call to a third-party model — they would be slow, flaky, and would burn free-tier
    quota. The LLM path is exercised by scripts/scenario_smoke.py instead.
    """
    settings = get_settings()
    original = settings.agent_mode
    settings.agent_mode = "rule"
    yield
    settings.agent_mode = original


@pytest.fixture(autouse=True)
def clean_state():
    store.reset()
    simulator.reseed()
    yield
    store.reset()
    simulator.reseed()
