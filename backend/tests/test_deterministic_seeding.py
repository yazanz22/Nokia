"""The simulator must produce the same telemetry after a restart.

``store`` advertises that the demo "starts from a clean, deterministic seed every
time", and the rehearsal-then-perform shape of a live demo depends on it. The
per-asset samplers used to seed from the builtin ``hash()``, which Python salts
per interpreter (PYTHONHASHSEED) — so the claim was false across restarts and no
single-process test could have caught it: within one process the salt is fixed,
so an in-process ``assert build_profiles(...) == build_profiles(...)`` passes
whether the bug is present or not.

These tests therefore run the seeding in two *separate* interpreters under two
different hash seeds, and a guard asserts that the salt really did differ between
them — otherwise the comparison would be vacuous in the same way.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]

# Printed by the child: line 1 is a digest of the sampled telemetry, line 2 is the
# builtin salted hash of a string — the salt witness that keeps this test honest.
_CHILD = """
import hashlib, json, sys
sys.path.insert(0, {backend!r})
from app.seed import build_demo_fleet, build_technicians
from app.simulator.profiles import build_profiles

ids = ["EQ-0051", "EQ-0180", "EQ-0248", "EQ-0295"]
profiles = build_profiles(ids)
sampled = []
for aid in ids:
    profile = profiles[aid]
    for _ in range(5):
        sampled.append(profile.next_normal())
    for label in ("NETWORK_OUTAGE", "DEVICE_FAILURE", "SENSOR_FAILURE"):
        sampled.append(profile.next_row(label))

fleet = [(a.id, a.kind, a.site, a.latitude, a.longitude) for a in build_demo_fleet()]
crew = [(t.id, t.name, t.latitude, t.longitude, t.parts_on_hand) for t in build_technicians()]

blob = json.dumps([sampled, fleet, crew], sort_keys=True, default=str)
print(hashlib.sha256(blob.encode()).hexdigest())
print(hash("EQ-0051"))
"""


def _run(hash_seed: str) -> tuple[str, str]:
    env = {**os.environ, "PYTHONHASHSEED": hash_seed}
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD.format(backend=str(BACKEND))],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(BACKEND),
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr
    digest, salt_witness = proc.stdout.split()[:2]
    return digest, salt_witness


@pytest.fixture(scope="module")
def two_processes() -> tuple[tuple[str, str], tuple[str, str]]:
    return _run("1"), _run("2")


def test_hash_salt_actually_differs_between_the_two_processes(two_processes):
    """Guard: without this, an identical digest would prove nothing."""
    (_, salt_a), (_, salt_b) = two_processes
    assert salt_a != salt_b, (
        "PYTHONHASHSEED did not change the builtin hash between the two child "
        "processes, so the determinism assertion below is vacuous"
    )


def test_simulator_seeding_is_stable_across_processes(two_processes):
    (digest_a, _), (digest_b, _) = two_processes
    assert digest_a == digest_b, (
        "the simulator, demo fleet or crew changed between two interpreters that "
        "differ only in PYTHONHASHSEED — something is seeded from the builtin hash()"
    )


def test_profiles_never_call_the_builtin_hash(monkeypatch):
    """A fast in-process guard, for the sake of a legible failure.

    The cross-process tests above are the real proof; this one just says *why* they
    would fail. Patching ``builtins.hash`` only intercepts Python-level calls —
    dict and set lookups hash through the C API and are unaffected.
    """
    import builtins

    from app.simulator.profiles import build_profiles

    def forbidden(_obj):  # pragma: no cover - only runs on regression
        raise AssertionError("build_profiles called the salted builtin hash()")

    monkeypatch.setattr(builtins, "hash", forbidden)
    profiles = build_profiles(["EQ-0051", "EQ-0180"])
    assert profiles["EQ-0051"].next_normal() is not None
