import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.simulator import simulator  # noqa: E402
from app.store import store  # noqa: E402


@pytest.fixture(autouse=True)
def clean_state():
    store.reset()
    simulator.reseed()
    yield
    store.reset()
    simulator.reseed()
