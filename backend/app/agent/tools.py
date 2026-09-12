"""Concrete actions the agent can take.

These are plain async functions with no tracing inside them. The rule agent calls
them directly; the Pydantic AI agent registers thin wrappers as tools. Keeping the
logic here means both agent modes take *exactly* the same actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import NamedTuple

from ..models import FaultPrediction, TelemetrySample, Technician, WorkOrder, utcnow
from ..nac import DeviceLocation, NetworkClient, Reachability, get_network_client
# One haversine for the whole backend. It lives in nac/base.py beside SITE_CENTER,
# where the geofence, the simulator and the seed already measure with it; dispatch
# distances have to come out of the same function as perimeter distances or the map
# and the work order can disagree about what a kilometre is. Bound under the
# module-private name the dispatch code below reads with.
from ..config import get_settings
from ..nac.base import haversine_km as _haversine_km
from ..seed import VAN_STOCK
from ..nac.factory import get_simulated_client
from ..ml.client import fault_model
from ..events import bus
from ..models import WsEvent
from ..store import store
from .memory import memory

# Serving-cell signal at/below this (dBm) is "weak"; combined with neighbour-cell
# failures it points to a genuine coverage gap rather than a dead machine.
WEAK_SIGNAL_DBM = -105.0

# The fleet's home network. NEOM sits at the head of the Gulf of Aqaba, within a few
# kilometres of Egyptian and Jordanian networks, so border roaming is a real event
# on this site rather than a hypothetical.
HOME_COUNTRY = "SA"

# CAMARA Congestion Insights grades the serving area, not the device — which makes it
# the one piece of coverage evidence that still arrives when the device is dark. It is
# the fallback, never the override: where the radio metrics exist they are specific to
# this device at the moment it went quiet, and a congested area is only ever a
# statement about the neighbourhood.
CONGESTION_BLAMES_NETWORK = {"High"}
CONGESTION_CLEARS_NETWORK = {"None", "Low"}

# Congestion Insights reports how sure the operator is, and below half sure it is not
# evidence — it is a guess with a number attached. Acting on it either way is a real
# mistake in both directions: withhold a dispatch on a low-confidence "High" and a
# broken machine sits in the desert; spend one on a low-confidence "Low" and a truck
# rolls for nothing. Under this floor the reading is reported and ignored, and the
# silence falls through to the fault model as it did before.
MIN_CONGESTION_CONFIDENCE = 50


def _client_for(subject_id: str) -> NetworkClient:
    """The client that can actually answer for this subject.

    Assets and technicians are simulated. They are not SIMs on the Nokia sandbox and
    never will be, so in live mode an unmapped subject falls through to
    ``nac_default_device`` — the single shared test SIM, which sits in Hungary and
    always reports ``roaming: true, country: HU``. Since ``assess_silence`` checks
    roaming first and ``HU != SA``, every incident closed as roaming: no ML, no
    Location Retrieval, no work order, ever, whichever scenario was injected.

    A subject with a device of its own in ``NAC_DEVICE_MAP`` is asked for real. Anyone
    else is asked of the simulation they actually live in. One helper for assets and
    crew both, so the two rules cannot drift apart again — they already had, and only
    the crew half was guarded.
    """
    from ..config import get_settings

    settings = get_settings()
    if settings.nac_mode == "live" and subject_id not in settings.device_map():
        return get_simulated_client()
    return get_network_client()


async def check_device_status(asset_id: str) -> Reachability:
    return await _client_for(asset_id).get_reachability(asset_id)


async def get_device_location(asset_id: str) -> DeviceLocation:
    return await _client_for(asset_id).get_location(asset_id)


class SilenceVerdict(NamedTuple):
    """Why an asset went quiet, and whether that justifies sending anyone."""

    dispatch: bool          # should we go down the fault / dispatch path at all?
    category: str           # coverage_gap | roaming_out | hardware | inconclusive
    explanation: str


def assess_silence(reach: Reachability) -> SilenceVerdict:
    """Work out why a machine stopped reporting.

    Silence has more than one cause, and they need opposite responses. Reachability
    alone cannot separate them — that is the whole reason this calls more than one
    CAMARA API.
    """
    sig = reach.signal_strength_dbm
    nbr = reach.neighbor_fail_count or 0

    # Attached to a foreign network. The device is alive and on a network, it just
    # is not on OURS — so our telemetry APN never reaches the fleet backend. This is
    # invisible to reachability and to any on-board sensor; only the roaming API
    # reports it. It is a connectivity ticket, never a mechanic.
    if reach.roaming and reach.country and reach.country != HOME_COUNTRY:
        return SilenceVerdict(
            dispatch=False,
            category="roaming_out",
            explanation=(
                f"The device is reachable but roaming on a {reach.country} network. It has "
                "crossed onto a foreign operator near the site boundary, so its telemetry APN "
                "no longer reaches us. The machine is fine — this is a connectivity ticket, "
                "not a breakdown."
            ),
        )

    # Attached, but for SMS only — the operator reports no data session. Telemetry
    # travels over data, so the network already explains this silence before the
    # machine is in question: the modem has power and is registered, it just has no
    # bearer to send on. This used to fall through to the branch below as
    # "connected", which told both agents connectivity was ruled out and sent a
    # mechanic to a machine that could not have reported its state either way. It
    # takes the coverage response instead, so both agents and the automated re-check
    # route it exactly as they route a coverage gap: logged, re-checked, nobody sent.
    if reach.status == "CONNECTED_SMS":
        return SilenceVerdict(
            dispatch=False,
            category="coverage_gap",
            explanation=(
                "The SIM is attached to our network for SMS only — the operator reports no "
                "data session. Telemetry needs data, so the network explains the silence; "
                "nothing on the machine is in question yet."
            ),
        )

    if reach.data_connected:
        # Attached to our own network yet not reporting. Connectivity is ruled out, so
        # this still needs the fault model — it is how a failed sensor on a healthy
        # machine presents, and how a transient dropout presents too.
        return SilenceVerdict(
            True, "inconclusive",
            "SIM is attached to our network — connectivity is not the problem, so the "
            "silence is something on the machine.",
        )

    if sig is not None and sig <= WEAK_SIGNAL_DBM and nbr >= 1:
        return SilenceVerdict(
            dispatch=False,
            category="coverage_gap",
            explanation=(
                f"Last serving-cell signal {sig:.0f} dBm with {nbr} neighbour-cell failures — "
                "the network dropped the device, not a fault on the machine."
            ),
        )

    if sig is not None and sig > WEAK_SIGNAL_DBM and nbr == 0:
        return SilenceVerdict(
            dispatch=True,
            category="hardware",
            explanation=(
                f"Device is unreachable but its last serving-cell signal was strong ({sig:.0f} dBm) "
                "with no neighbour-cell failures — the network is healthy here, so the silence is "
                "the equipment itself."
            ),
        )

    # No radio metrics. This is the normal case against a real operator: CAMARA Device
    # Status reports attachment and says nothing about signal, so without a second
    # source every coverage gap would present as a possible breakdown and get someone
    # sent. Congestion Insights is that second source.
    if sig is None and reach.congestion_level:
        conf = reach.congestion_confidence
        conf_text = f" at {conf}% confidence" if conf is not None else ""
        # A reading the operator is not confident in decides nothing. Say so out loud
        # rather than quietly discarding it — the number is on the dashboard, and an
        # operator who can see "High" needs to know why it did not count.
        if conf is not None and conf < MIN_CONGESTION_CONFIDENCE:
            return SilenceVerdict(
                True, "inconclusive",
                f"The operator reports {reach.congestion_level.lower()} congestion here but only "
                f"{conf}% confidence in that reading, which is too weak to decide either way. "
                "Treating the silence as a possible fault and handing it to the model.",
            )
        if reach.congestion_level in CONGESTION_BLAMES_NETWORK:
            return SilenceVerdict(
                dispatch=False,
                category="coverage_gap",
                explanation=(
                    f"No radio metrics from Device Status, but the operator reports "
                    f"{reach.congestion_level.lower()} congestion in this serving area"
                    f"{conf_text}. The device went quiet into a network that is already "
                    "struggling here — that is a coverage failure, not a breakdown."
                ),
            )
        if reach.congestion_level in CONGESTION_CLEARS_NETWORK:
            return SilenceVerdict(
                dispatch=True,
                category="hardware",
                explanation=(
                    f"The operator reports {reach.congestion_level.lower()} congestion in this "
                    f"serving area{conf_text}, so the network here is healthy. The device is "
                    "unreachable anyway — the silence is the equipment."
                ),
            )

    # Ambiguous — lean toward investigating hardware (a wasted check beats a missed breakdown).
    return SilenceVerdict(
        True, "inconclusive",
        "Network signal inconclusive; treating as a possible hardware fault pending ML review.",
    )


def predict_fault(asset_id: str, reach: Reachability | None = None) -> FaultPrediction:
    """Classify the fault from what the agent knows *now*.

    The last frame a machine transmitted is stamped reachable-and-fresh — it arrived,
    after all. But by the time we classify, the machine has gone quiet, and that
    silence is itself evidence. So we take the physical channels from the last frame
    and overlay the current network reality: whether CAMARA can still see the device,
    and how long it has actually been dark.

    Without this the model is asked about a state that never occurs in training
    (a red-hot engine on a device that is still answering) and extrapolates badly.
    """
    last = store.latest_telemetry.get(asset_id)
    if last is None:
        last = TelemetrySample(asset_id=asset_id)

    asset = store.assets.get(asset_id)
    silence_s = (utcnow() - asset.last_seen).total_seconds() if asset else last.telemetry_age_sec

    sample = last.model_copy(
        update={
            "reachable": reach.data_connected if reach is not None else last.reachable,
            "telemetry_age_sec": max(last.telemetry_age_sec, silence_s),
            "signal_strength_dbm": (
                reach.signal_strength_dbm
                if reach is not None and reach.signal_strength_dbm is not None
                else last.signal_strength_dbm
            ),
            "neighbor_fail_count": (
                reach.neighbor_fail_count
                if reach is not None and reach.neighbor_fail_count is not None
                else last.neighbor_fail_count
            ),
        }
    )
    return fault_model.predict(asset_id, sample)


# The call sites express the re-check interval in operational minutes — 15 for a
# coverage gap, 30 for a border-roaming ticket, which is the ratio an ops team would
# actually choose. Nothing in a five-minute demo can wait fifteen real minutes, so the
# nominal minutes are compressed onto a demo clock: RECHECK_AFTER_SECONDS of wall time
# per this many nominal minutes. Same trick as WORK_ORDER_COMPLETE_SECONDS, and for the
# same reason — a promise nobody in the room can stay to see is indistinguishable from
# no promise at all. The ratio is preserved so a roaming ticket still waits twice as
# long as a blind spot.
RECHECK_NOMINAL_MINUTES = 15.0


@dataclass
class PendingRecheck:
    """A re-check the agent told an operator it had queued.

    This used to be nothing: ``schedule_recheck`` returned a timestamp and dropped it
    on the floor. The trace said "re-check queued", the resolution said "Re-check at
    14:32 UTC", the asset was parked in ``blindspot`` — a state the anomaly sweep skips
    forever — and no re-check existed anywhere in the process. The machine stayed dark
    until somebody hit Reset. The registry below is what makes the sentence true: the
    detector's sweep reads it and actually goes and looks again.
    """

    asset_id: str
    incident_id: str          # where the re-check reports back, "" if it has no incident
    due_at: datetime
    interval_seconds: float   # what to wait again if the network is still down
    attempts: int = 0         # re-checks already run for this asset
    epoch: int = 0            # store.epoch when scheduled — a reset invalidates it


# asset_id -> the one outstanding re-check for it. One per asset: a second incident on
# the same machine replaces the promise rather than stacking a second timer onto it.
_pending_rechecks: dict[str, PendingRecheck] = {}


def _incident_for(asset_id: str) -> str:
    """The incident this re-check belongs under — its most recent one.

    Both agents call ``schedule_recheck`` while the incident is still open, just before
    closing it, so the newest incident for the asset is always the one making the
    promise. Looked up rather than passed in because the call sites live in the two
    agent modules and both must keep taking exactly the same action.
    """
    incidents = [i for i in store.incidents.values() if i.asset_id == asset_id]
    if not incidents:
        return ""
    return max(incidents, key=lambda i: i.opened_at).id


def schedule_recheck(asset_id: str, minutes: int = 15) -> datetime:
    """Queue a real re-check and return when it will run.

    The returned time is what the trace and the incident resolution print, so it has to
    be the time the detector will actually act on — otherwise the text and the behaviour
    disagree again, only more convincingly.
    """
    from ..config import get_settings

    interval = get_settings().recheck_after_seconds * (minutes / RECHECK_NOMINAL_MINUTES)
    due_at = utcnow() + timedelta(seconds=interval)
    _pending_rechecks[asset_id] = PendingRecheck(
        asset_id=asset_id,
        incident_id=_incident_for(asset_id),
        due_at=due_at,
        interval_seconds=interval,
        epoch=store.epoch,
    )
    return due_at


def reschedule_recheck(pending: PendingRecheck, *, count_attempt: bool = True) -> datetime:
    """Wait the same interval again — the network has not come back yet.

    ``count_attempt=False`` for a re-check that never got an answer at all: an API
    timeout says nothing about the machine, and letting a flapping endpoint burn the
    attempt budget would stand the re-check down without ever having looked.
    """
    if count_attempt:
        pending.attempts += 1
    pending.due_at = utcnow() + timedelta(seconds=pending.interval_seconds)
    _pending_rechecks[pending.asset_id] = pending
    return pending.due_at


def due_rechecks(now: datetime | None = None) -> list[PendingRecheck]:
    """Re-checks whose time has come.

    Entries scheduled before a reset are dropped here rather than run. ``store.reset()``
    is reachable without ``detector.reset()`` — the smoke script and the test fixtures
    both do exactly that — so an epoch stamp is what stops a re-check queued against the
    old fleet from firing at an asset in the new one.
    """
    now = now or utcnow()
    stale = [a for a, p in _pending_rechecks.items() if p.epoch != store.epoch]
    for asset_id in stale:
        _pending_rechecks.pop(asset_id, None)
    return [p for p in _pending_rechecks.values() if p.due_at <= now]


def pending_recheck(asset_id: str) -> PendingRecheck | None:
    return _pending_rechecks.get(asset_id)


def cancel_recheck(asset_id: str) -> None:
    _pending_rechecks.pop(asset_id, None)


def clear_rechecks() -> None:
    _pending_rechecks.clear()


def notify_operator(asset_id: str, message: str) -> str:
    """Raise a ticket with the humans, without sending anyone into the desert.

    In production this fans out to the ops channel / PagerDuty; here the dashboard
    incident feed is the notification surface, so the honest thing this returns is the
    line the operator sees. Both agents call it on the roaming branch and use the
    result as the trace step's observation — the step is labelled with this tool's
    name, and a trace that names a tool it did not invoke is a trace that cannot be
    trusted on the steps where it matters.
    """
    return f"Operator notified — {asset_id}: {message}"


async def locate_crew(technicians: list[Technician]) -> str:
    """Ask the network where the available crew actually are.

    A technician's phone is a device on the same network as the machine, so the same
    CAMARA Location Retrieval call answers both halves of the dispatch question: where
    is the broken asset, and who is genuinely nearest to it. Rostered or last-known
    positions go stale the moment someone drives to a job — dispatching on them is how
    you send the second-nearest person.

    Best effort: a technician we cannot locate keeps their last known position rather
    than dropping out of consideration.
    """
    # In live mode an unmapped subject would fall back to the shared sandbox device,
    # putting every technician on the same coordinates and making "nearest" meaningless.
    # A technician with a device of their own is located for real; everyone else is
    # located against the simulation they actually exist in. Same rule as the assets,
    # from the same helper.
    #
    # The earlier version simply skipped them, and NAC_DEVICE_MAP is empty by default
    # — so in live mode nobody was located at all. Crews silently kept their seed
    # positions, the card quietly dropped its "network-located" tag, and the agent went
    # on narrating that it had just asked the network where they were.
    source = "seed"
    for tech in technicians:
        subject_client = _client_for(tech.id)
        try:
            loc = await subject_client.get_location(tech.id)
        except Exception:  # noqa: BLE001 - an unlocatable crew member is not fatal
            continue
        tech.latitude = loc.latitude
        tech.longitude = loc.longitude
        tech.located_via = loc.source
        source = loc.source
    return source


def queued_order_for(asset_id: str) -> WorkOrder | None:
    """The job already waiting on a free technician for this machine, if any.

    One machine gets one job. A queued job deliberately leaves its asset in a state the
    anomaly sweep still looks at, so the same fault *will* be investigated again — and
    that second run has to pick the waiting job up rather than stack a duplicate beside
    it. Keyed on the asset rather than the incident for exactly that reason: the second
    investigation is a different incident about the same broken machine.
    """
    return next(
        (
            w
            for w in store.work_orders.values()
            if w.asset_id == asset_id and w.status in ("queued", "awaiting_part")
        ),
        None,
    )


def _record_queued(wo: WorkOrder) -> None:
    """Register a job nobody is free to take — without calling it a dispatch.

    ``store.add_work_order`` is the only path that both stores an order and tells the
    dashboards about it, and it counts everything it registers into
    ``dispatches_issued``. That is right for a job with somebody driving to it and wrong
    for one sitting in a queue: the KPI is the number of trucks we actually rolled, and
    a queued job rolled none. The count is handed back here and paid for later, when the
    same order is registered again with a technician on it.

    Only when the order was actually taken: ``add_work_order`` refuses one built for a
    fleet that has since been reset, and un-counting a dispatch that was never counted
    would quietly cancel somebody else's.
    """
    if store.add_work_order(wo):
        store.dispatches_issued = max(0, store.dispatches_issued - 1)


def unassigned_thought(wo: WorkOrder) -> str:
    """The agent's own words for a job it could not hand to anybody.

    Two different blockers, two different sentences, one source for both. A crew that
    is fully committed is a scheduling problem that resolves itself within the hour; a
    component no depot on site holds does not resolve at all until somebody orders one,
    and telling an operator "waiting for a technician" when the truth is "waiting for a
    part" sends them to argue with the wrong person.
    """
    if wo.status == "awaiting_part":
        return (
            f"The fault is confirmed and the part is named, but no depot on site holds a "
            f"{wo.part}. There is nothing for a technician to collect, so sending one now "
            f"would be a wasted journey with a diagnosis at the end of it. The job is "
            f"raised against the machine and flagged for resupply, and the machine stays "
            f"on the sweep."
        )
    return (
        "The job is ready but every technician on the crew is already out on one. I am not "
        "going to record a dispatch that is not happening: the work order is raised "
        "unassigned, and the machine stays on the sweep so it is picked up the moment "
        "somebody frees."
    )


def queued_observation(wo: WorkOrder) -> str:
    """What the trace says about a job that could not be given to anyone.

    Shared by both agents so the two cannot describe the same outcome differently.
    """
    if wo.status == "awaiting_part":
        stocked = store.stock_on_hand(wo.part)
        where = (
            "; nearest stock is " + ", ".join(sorted(stocked)) if stocked else " at any depot"
        )
        return (
            f"{wo.id} raised against {wo.asset_id} but blocked: no {wo.part} in stock"
            f"{where} — flagged for resupply, nobody dispatched"
        )
    crew = len(store.technicians)
    busy = sum(1 for t in store.technicians.values() if not t.available)
    return (
        f"{wo.id} queued unassigned carrying {wo.part or 'n/a'} — {busy}/{crew} technicians "
        "are already on jobs, so there is no name and no ETA to put on it yet"
    )


def dispatch_thought(wo: WorkOrder) -> str:
    """The agent's own words for an assignment that is going ahead.

    The old wording claimed the assignment went to "the nearest technician who is
    actually carrying the part", which stopped being true the moment components moved
    into depots. Now the sentence has to explain a two-leg journey, and it is shared so
    it cannot say one thing in the LLM agent and another in the rule agent.
    """
    if wo.warehouse_id:
        return (
            f"Work order raised. The {wo.part} is a depot item, so the journey is "
            f"technician to {wo.warehouse_name}, load, then on to the machine — and the "
            f"person who arrives first is the one with the shortest combined run, not the "
            f"one standing nearest. Assigned on arrival time."
        )
    return (
        "Work order raised. The part rides in the van, so there is no depot to collect "
        "from and the nearest technician is also the soonest."
    )


def dispatch_observation(wo: WorkOrder) -> str:
    """The recorded outcome of an assignment. Shared by both agents."""
    route = (
        f"{wo.leg_to_warehouse_km:.1f} km to {wo.warehouse_name}, "
        f"{wo.loading_minutes} min loading, {wo.leg_to_asset_km:.1f} km on"
        if wo.warehouse_id
        else f"{wo.distance_km:.1f} km direct"
    )
    out = (
        f"{wo.id} -> {wo.technician_name or 'unassigned'} carrying {wo.part or 'n/a'} "
        f"({route}; ETA {wo.eta_minutes} min); crew position source="
        f"{wo.technician_located_via}"
    )
    if wo.nearest_skipped_name:
        out += (
            f". {wo.nearest_skipped_name} is nearer the machine at "
            f"{wo.nearest_skipped_km:.1f} km but would arrive "
            f"{wo.nearest_skipped_minutes_later} min later once the part is collected — "
            f"closer is not sooner when the part is not in the van."
        )
    return out


def park_awaiting_crew(
    incident_id: str,
    asset_id: str,
    wo: WorkOrder,
    fault: FaultPrediction,
) -> str:
    """Close out a confirmed fault that has a job but nobody going to it.

    Two reasons that happens — no free technician, or no depot holding the component —
    and the incident records which. Named for the crew case because that is the one it
    was written for; it covers both because both must produce the same honest shape of
    record, and splitting it into two near-identical functions is how they drift.

    The whole crew being busy used to produce a record that contradicted itself: the
    work order was written as ``status="created"`` with no technician and a zero ETA,
    the resolution read "dispatched to  (ETA 0 min)", and the asset was parked in
    ``dispatched`` — which the freshness sweep skips. A machine nobody was driving to
    was also a machine nobody was watching, and it stayed that way until a reset.

    So the honest version: the job is queued and says so, and the asset goes back to
    ``anomaly``. That is not a cosmetic choice — ``anomaly`` is swept by the detector,
    is returned to service by ``complete_work_order``/``delete_work_order``, and lets
    ``record_telemetry`` advance ``last_seen`` if the machine starts talking again, so
    every existing recovery path still works on it. ``last_seen`` is stamped now so the
    sweep waits one full silent-threshold before re-opening rather than firing on the
    next 2s pass; that re-investigation is what hands the queued job to the first
    technician who frees.

    Both agents call this and nothing else on this path — the two must not drift.
    Returns the resolution text.
    """
    inc = store.incidents[incident_id]
    asset = store.assets.get(asset_id)
    crew = len(store.technicians)
    component = f" ({fault.component.replace('_', ' ')})" if fault.component else ""
    if wo.status == "awaiting_part":
        status = "awaiting_part"
        resolution = (
            f"{fault.mode} confirmed @ {fault.confidence:.0%}{component}, but no depot on "
            f"site stocks a {wo.part}. {wo.id} is raised against the machine and flagged "
            f"for resupply — nobody is en route, because there is nothing for them to "
            f"collect. The machine stays under watch and the job releases when the part "
            f"lands."
        )
    else:
        status = "awaiting_crew"
        resolution = (
            f"{fault.mode} confirmed @ {fault.confidence:.0%}{component}, but all {crew} "
            f"technicians are already on jobs. {wo.id} is queued unassigned with "
            f"{wo.part or 'no part'} against it — nobody is en route and no ETA is promised. "
            f"The machine stays under watch and the job goes to the first technician who frees."
        )
    store.set_asset_state(asset_id, "anomaly", last_seen=utcnow())
    store.close_incident(inc, status=status, resolution=resolution)
    if asset is not None:
        memory.record(asset_id, asset.latitude, asset.longitude, status)
    store.publish_kpis()
    return resolution


# ── routing constants ───────────────────────────────────────────────────────
# Effective speed across a live construction site, and the time between a job landing
# and the van actually moving. Both were already baked into the old single-leg ETA;
# they are named here because the journey now has two legs and a dwell in the middle,
# and a magic 45 buried twice in an arithmetic expression is how two halves drift
# apart.
SITE_SPEED_KMH = 45.0
MOBILISATION_MINUTES = 10


def _travel_minutes(km: float) -> float:
    return km / SITE_SPEED_KMH * 60.0


def _route_options(
    crew: list[Technician],
    parts: list[str],
    asset_lat: float,
    asset_lon: float,
) -> list[tuple[float, Technician, str, float, float]]:
    """Every way of getting ``parts`` to the machine, ranked by arrival time.

    Returns ``(total_minutes, technician, warehouse_id, leg1_km, leg2_km)``, soonest
    first. Parts that ride in the van impose no depot leg; if nothing on the list has
    to be collected, ``warehouse_id`` is empty and the run is direct.

    This is the change a field-service reviewer asked for. Dispatching on
    distance-to-machine is only correct when the technician already has what they need;
    the moment the part lives in a depot, the person who arrives first is the one whose
    *combined* journey is shortest, and that is frequently not the nearest one. Ranked
    rather than reduced to a single winner so the caller can walk down the list when a
    depot is emptied by a dispatch running alongside this one.
    """
    loading = get_settings().warehouse_loading_minutes
    depot_parts = [p for p in parts if p and p not in VAN_STOCK]
    options: list[tuple[float, Technician, str, float, float]] = []

    if not depot_parts:
        # Straight there. A telemetry sensor kit is a box in the back of the van, so a
        # sensor fault never inherits a depot detour it does not need — which is also
        # what keeps the graded response graded: the cheap outcome stays cheap.
        for t in crew:
            leg = _haversine_km(t.latitude, t.longitude, asset_lat, asset_lon)
            options.append((_travel_minutes(leg) + MOBILISATION_MINUTES, t, "", 0.0, leg))
        options.sort(key=lambda o: o[0])
        return options

    for wh_id in store.depots_stocking(depot_parts):
        wh = store.warehouses[wh_id]
        leg2 = _haversine_km(wh.latitude, wh.longitude, asset_lat, asset_lon)
        for t in crew:
            leg1 = _haversine_km(t.latitude, t.longitude, wh.latitude, wh.longitude)
            total = _travel_minutes(leg1 + leg2) + loading + MOBILISATION_MINUTES
            options.append((total, t, wh_id, leg1, leg2))
    options.sort(key=lambda o: o[0])
    return options


def _choose_and_claim(
    free: list[Technician],
    parts: list[str],
    asset_lat: float,
    asset_lon: float,
) -> tuple[Technician | None, str, float, float, float]:
    """Pick the soonest workable route and take its technician and stock off the board.

    Synchronous from the first read to the last claim, and it has to stay that way. The
    caller has just spent ~3.6s on CAMARA Location Retrieval, which is ample room for a
    second investigation to decide from the same snapshot — that is how two work orders
    were once issued to one technician. Stock has the same exposure with a worse failure
    mode, because it is invisible: two investigations needing the last alternator would
    both be promised it, and the second technician would find the empty shelf only after
    driving to the depot.

    Walks the ranked routes rather than committing to the best one, so a depot emptied
    between ranking and claiming costs this dispatch its first choice instead of its
    dispatch.
    """
    depot_parts = [p for p in parts if p and p not in VAN_STOCK]
    for total, cand, wh_id, l1, l2 in _route_options(free, parts, asset_lat, asset_lon):
        claimed: list[str] = []
        if wh_id:
            for p in depot_parts:
                if store.claim_part(wh_id, p):
                    claimed.append(p)
                else:
                    break
            if len(claimed) != len(depot_parts):
                for p in claimed:
                    store.release_part(wh_id, p)
                continue
        if not store.claim_technician(cand):
            # Nothing above yields, so this cannot lose in practice — but stock claimed
            # for a technician we did not get would sit off the shelf forever.
            for p in claimed:
                store.release_part(wh_id, p)
            continue
        return cand, wh_id, l1, l2, total
    return None, "", 0.0, 0.0, 0.0


async def create_work_order(
    incident_id: str,
    asset_id: str,
    fault: FaultPrediction,
    location: DeviceLocation,
) -> WorkOrder:
    part = fault.recommended_part

    # Establish where the whole available crew is *now*, once. Every question below —
    # who reaches the machine soonest, and who was nearer but slower — is answered from
    # the same set of positions. Locating twice would bill the Location Retrieval API
    # twice per dispatch and, worse, compare people measured at different moments.
    available = [t for t in store.technicians.values() if t.available]
    crew_source = await locate_crew(available)

    # ── choose and claim, with no await in between ──────────────────────────────
    # Everything from here down to the claims is deliberately synchronous. The list
    # above is ~3.6s stale by the time we get here — locating the crew is serial and
    # each CAMARA round trip costs 0.6s — which is ample room for a second
    # investigation to run its own dispatch alongside this one. It did: two faults
    # injected a few seconds apart produced WO-0002 and WO-0003 both assigned to Ziad
    # Khalifeh, because both runs decided from a snapshot taken before either had
    # claimed anybody. Stock is now on the same footing, and its failure mode is worse
    # because it is invisible: two investigations needing the last alternator would
    # both be promised it, and the second technician would find the empty shelf only
    # after driving to the depot.
    free = [t for t in available if t.available]

    # A part nobody stocks is a different problem from a crew nobody has spare, and the
    # work order says which. Checked before the ranking so the distinction survives the
    # case where both are true at once.
    part_unavailable = (
        bool(part) and part not in VAN_STOCK and not store.depots_stocking([part])
    )
    tech: Technician | None = None
    warehouse_id = ""
    leg1 = leg2 = total_minutes = 0.0
    if free and not part_unavailable:
        tech, warehouse_id, leg1, leg2, total_minutes = _choose_and_claim(
            free, [part], location.latitude, location.longitude
        )
    # ── end of the critical section ─────────────────────────────────────────────

    # Who was *nearest the machine*, and how much later they would actually have
    # arrived. On a map, driving past a closer person looks like a bug; this is the
    # line that explains it. Same idea as the field it replaces — which named someone
    # closer who was not carrying the part — measured in the unit that now decides it.
    skipped_name = ""
    skipped_km = 0.0
    skipped_later = 0
    if tech is not None and free:
        nearest, nearest_km = min(
            (
                (t, _haversine_km(t.latitude, t.longitude, location.latitude, location.longitude))
                for t in free
            ),
            key=lambda pair: pair[1],
        )
        chosen_km = _haversine_km(
            tech.latitude, tech.longitude, location.latitude, location.longitude
        )
        # Compare what will actually be displayed, not full float precision: both
        # numbers reach the card rounded to a tenth, and someone "nearer" by eight
        # metres produced a card that contradicted itself across its own two lines.
        if nearest.id != tech.id and round(nearest_km, 1) < round(chosen_km, 1):
            theirs = _route_options([nearest], [part], location.latitude, location.longitude)
            if theirs and theirs[0][0] > total_minutes:
                skipped_name = nearest.name
                skipped_km = round(nearest_km, 1)
                skipped_later = int(round(theirs[0][0] - total_minutes))

    # A job already waiting on this machine is *this* job — the re-investigation that an
    # unassigned order deliberately invites. Reuse its id so the operator watches one
    # card change status instead of collecting a new card every sweep.
    waiting = queued_order_for(asset_id)

    if tech is not None:
        status = "assigned"
    elif part_unavailable:
        status = "awaiting_part"
    else:
        status = "queued"

    wh = store.warehouses.get(warehouse_id) if warehouse_id else None
    wo = WorkOrder(
        id=waiting.id if waiting is not None else store.next_work_order_id(),
        incident_id=incident_id,
        asset_id=asset_id,
        # Never "created" without somebody on it: a work order with no technician is
        # not a dispatch, and both the card and the incident record say so out loud.
        status=status,
        maintenance_type="corrective",
        fault_mode=fault.mode,
        component=fault.component,
        confidence=fault.confidence,
        component_confidence=fault.component_confidence,
        part=part,
        parts=[part] if part else [],
        asset_latitude=location.latitude,
        asset_longitude=location.longitude,
        technician_id=tech.id if tech else None,
        technician_name=tech.name if tech else "",
        technician_located_via=crew_source,
        warehouse_id=warehouse_id,
        warehouse_name=wh.name if wh else "",
        leg_to_warehouse_km=round(leg1, 1),
        leg_to_asset_km=round(leg2, 1),
        loading_minutes=get_settings().warehouse_loading_minutes if warehouse_id else 0,
        distance_km=round(leg1 + leg2, 1),
        eta_minutes=int(round(total_minutes)) if tech else 0,
        nearest_skipped_name=skipped_name,
        nearest_skipped_km=skipped_km,
        nearest_skipped_minutes_later=skipped_later,
    )
    # `created_at` defaults to now, and that is deliberate on every branch. It is the
    # clock `store.advance_work_orders` runs the repair against — so it must start when
    # a technician actually takes the job, not while it sat unassigned, and re-queueing
    # has to push it forward or a waiting job would "complete" itself after
    # WORK_ORDER_COMPLETE_SECONDS with no one having gone anywhere.
    if tech is None:
        _record_queued(wo)
    else:
        store.add_work_order(wo)
    return wo


async def create_scheduled_work_order(
    asset_id: str,
    maintenance_type: str,
    parts: list[str],
    *,
    component: str = "",
    component_confidence: float = 0.0,
    bundled_service: bool = False,
    reason: str = "",
) -> WorkOrder:
    """Raise a planned visit — preventive or predictive — for a machine that has not failed.

    The counterpart to ``create_work_order``, and deliberately a separate entry point
    rather than a flag on it. That one starts from an incident, a fault classification
    and a network verdict, none of which exist here: nothing has broken, so there is
    nothing to diagnose and no silence to explain. What the two share is the part that
    matters — the same depot routing, the same atomic claim on stock and crew, and the
    same refusal to write a dispatch with nobody on it.

    Located from the machine's own recorded position rather than CAMARA Location
    Retrieval. That call earns its place when a device has gone dark and cannot report
    where it is; a machine that is running and streaming already told us, and spending
    a network lookup to re-learn it would be theatre.
    """
    asset = store.assets[asset_id]
    available = [t for t in store.technicians.values() if t.available]
    crew_source = await locate_crew(available)
    free = [t for t in available if t.available]

    wanted = [p for p in parts if p]
    depot_parts = [p for p in wanted if p not in VAN_STOCK]
    part_unavailable = bool(depot_parts) and not store.depots_stocking(depot_parts)

    tech: Technician | None = None
    warehouse_id = ""
    leg1 = leg2 = total_minutes = 0.0
    if free and not part_unavailable:
        tech, warehouse_id, leg1, leg2, total_minutes = _choose_and_claim(
            free, wanted, asset.latitude, asset.longitude
        )

    if tech is not None:
        status = "assigned"
    elif part_unavailable:
        status = "awaiting_part"
    else:
        status = "queued"

    wh = store.warehouses.get(warehouse_id) if warehouse_id else None
    wo = WorkOrder(
        id=store.next_work_order_id(),
        # No incident, and that is the point: this work is scheduled, not triggered by
        # something going wrong.
        incident_id="",
        asset_id=asset_id,
        status=status,
        maintenance_type=maintenance_type,  # type: ignore[arg-type]
        fault_mode=reason,
        component=component,
        component_confidence=component_confidence,
        part=wanted[0] if wanted else "",
        parts=wanted,
        bundled_service=bundled_service,
        asset_latitude=asset.latitude,
        asset_longitude=asset.longitude,
        technician_id=tech.id if tech else None,
        technician_name=tech.name if tech else "",
        technician_located_via=crew_source,
        warehouse_id=warehouse_id,
        warehouse_name=wh.name if wh else "",
        leg_to_warehouse_km=round(leg1, 1),
        leg_to_asset_km=round(leg2, 1),
        loading_minutes=get_settings().warehouse_loading_minutes if warehouse_id else 0,
        distance_km=round(leg1 + leg2, 1),
        eta_minutes=int(round(total_minutes)) if tech else 0,
    )
    if tech is None:
        _record_queued(wo)
    else:
        store.add_work_order(wo)
    return wo


def clear_service(asset_id: str) -> None:
    """Reset a machine's service clock. Called when a visit that serviced it finishes."""
    asset = store.assets.get(asset_id)
    if asset is None:
        return
    asset.hours_since_service = 0.0
    bus.publish(WsEvent(type="asset_update", payload=asset.model_dump(mode="json")))
