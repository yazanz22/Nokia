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


@pytest.fixture(autouse=True)
def pinned_agent_mode():
    """Restore ``agent_mode`` after every test, not just at the end of the session.

    ``get_settings()`` is a process-wide singleton and several tests flip
    ``agent_mode`` to "llm" in place to exercise the model path. The session-scoped
    fixture above puts it back once, at the very end — so a test that sets it and
    fails, or one whose restore is skipped, leaves every later test running under a
    mode it never asked for. That was diagnosed as the likeliest cause of an
    intermittent failure in test_llm_agent.py, where a run recorded itself as
    "rule (fallback)" with no error — only reachable if the mode changed underneath
    an investigation already in flight.
    """
    settings = get_settings()
    before = settings.agent_mode
    yield
    settings.agent_mode = before
