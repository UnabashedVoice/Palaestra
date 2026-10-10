"""
world.py — Loading and validating a world definition.

A world is a folder:

    worlds/<id>/world.json     the region: roles, parties, resources, labels,
                               the agenda (which event each role faces in which
                               round) and triggers (events that happen because
                               the state now calls for them)
    worlds/<id>/events/*.json  one event per file

Events are either:
    choice  a decision for one role. Its options come from a validated scenario
            (`from_scenario`: "family/variant") or an inline scenario family
            with the same schema. `ops` say what each option does to the world
            state; they may implement only what the option's stipulated effects
            state, with "unknown" outcomes left to scheduled `auto` events.
    auto    something that happens: resolved by the world's seeded chance, with
            `success` and `failure` branches.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from ..schema import SELF_PARTY, Perspective, Scenario, expand_family, validate_family

KNOWN_OPS = {"add", "set", "schedule", "conceal", "reveal", "decommission", "pause"}


@dataclass
class Event:
    id: str
    kind: str                         # "choice" | "auto"
    raw: dict
    scenario: Optional[Scenario] = None
    party_map: dict = field(default_factory=dict)


@dataclass
class World:
    id: str
    spec: dict
    events: dict[str, Event]

    @property
    def roles(self) -> list[str]:
        return list(self.spec["roles"])

    @property
    def variant(self) -> Optional[str]:
        return self.spec.get("variant")

    @property
    def fingerprint(self) -> str:
        return self.spec.get("fingerprint", "")


def _scenario_for(ev: dict, library: dict[str, Scenario], perspectives: dict[str, Perspective],
                  errors: list[str]) -> Optional[Scenario]:
    if "from_scenario" in ev:
        s = library.get(ev["from_scenario"])
        if s is None:
            errors.append(f"{ev['id']}: unknown scenario {ev['from_scenario']!r}")
        return s
    fam = ev.get("scenario")
    if fam is None:
        errors.append(f"{ev['id']}: choice event needs from_scenario or scenario")
        return None
    errs = validate_family(fam, perspectives)
    errors.extend(f"{ev['id']}: {e}" for e in errs)
    return None if errs else expand_family(fam)[0]


def _check_ops(where: str, ops: list[dict], errors: list[str]) -> None:
    for op in ops:
        if op.get("op") not in KNOWN_OPS:
            errors.append(f"{where}: unknown op {op.get('op')!r}")


_CONDITION_TESTS = {"eq", "ne", "gt", "lt"}


def _check_reply(where: str, reply, errors: list[str]) -> None:
    """A reply is text, or a list of conditional entries ending in one without
    a condition, so some entry always applies whatever state the world is in."""
    if isinstance(reply, str):
        return
    if not isinstance(reply, list) or not reply:
        errors.append(f"{where}: a reply must be text or a non-empty list of entries")
        return
    for i, r in enumerate(reply):
        last = i == len(reply) - 1
        if not isinstance(r, dict) or not isinstance(r.get("text"), str) or set(r) - {"when", "text"}:
            errors.append(f"{where}[{i}]: an entry needs \"text\" and may have \"when\", nothing else")
            continue
        if last and "when" in r:
            errors.append(f"{where}: the last entry must have no \"when\", so some reply always applies")
        if not last and not r.get("when"):
            errors.append(f"{where}[{i}]: only the last entry may lack a \"when\"")
        for c in r.get("when", []):
            if "ledger" not in c and not ("key" in c and len(_CONDITION_TESTS & set(c)) == 1):
                errors.append(f"{where}[{i}]: condition needs a key and one of eq, ne, gt, lt: {c}")


def _deep_merge(base: dict, over: dict) -> dict:
    """Dicts merge recursively; anything else (lists included) is replaced."""
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def _patch_scenario(s: Scenario, patch: dict) -> Scenario:
    """Same patch semantics as a scenario variant: named fields replaced,
    assessments merged per perspective, actions matched by id."""
    s = copy.deepcopy(s)
    for key in ("situation", "title", "parties"):
        if key in patch:
            setattr(s, key, copy.deepcopy(patch[key]))
    for aid, ap in patch.get("actions", {}).items():
        action = s.action(aid)
        for k, v in ap.items():
            if k == "assessments":
                action["assessments"].update(copy.deepcopy(v))
            else:
                action[k] = copy.deepcopy(v)
    s.actions.extend(copy.deepcopy(patch.get("add_actions", [])))
    return s


def _as_family(s: Scenario) -> dict:
    return {"family": s.family, "domain": s.domain, "title": s.title, "situation": s.situation,
            "parties": s.parties, "actions": s.actions, "authored_by": "(checked after patching)"}


def load_world(world_dir: Path, library: list[Scenario], perspectives: dict[str, Perspective],
               variant: Optional[str] = None) -> tuple[World, list[str]]:
    """Load a world, optionally with one of its declared variants applied.

    A variant (world.json "variants") changes one thing about the world and
    everything that follows from it: preamble additions, party overrides,
    label overrides, extra triggers, and per-event overlays. An event overlay
    is either the id of another event file to use in its place, or a dict
    deep-merged into the event (so it can swap `from_scenario`, replace ops or
    chronicle lines, or rewrite an automatic outcome's text), plus an optional
    `scenario_patch` applied to the event's options."""
    spec = json.loads((world_dir / "world.json").read_text(encoding="utf-8"))
    lib = {s.scenario_id: s for s in library}
    errors: list[str] = []
    events: dict[str, Event] = {}

    raw_events = {}
    for path in sorted((world_dir / "events").glob("*.json")):
        ev = json.loads(path.read_text(encoding="utf-8"))
        if ev.get("id", path.stem) != path.stem:
            errors.append(f"{path.name}: id {ev.get('id')!r} does not match filename")
        raw_events[path.stem] = ev

    patches = {}
    if variant is not None:
        overlay = spec.get("variants", {}).get(variant)
        if overlay is None:
            return World(id=spec["id"], spec=spec, events={}), [f"unknown variant {variant!r}"]
        spec = copy.deepcopy(spec)
        spec["variant"] = variant
        if overlay.get("preamble"):
            spec["preamble"] = overlay["preamble"]
        if overlay.get("preamble_append"):
            spec["preamble"] += " " + overlay["preamble_append"]
        spec["parties"] = _deep_merge(spec["parties"], overlay.get("parties", {}))
        spec["labels"] = {**spec.get("labels", {}), **overlay.get("labels", {})}
        spec["triggers"] = spec.get("triggers", []) + overlay.get("triggers_append", [])
        for eid, ov in overlay.get("events", {}).items():
            if eid not in raw_events:
                errors.append(f"variant {variant}: overlay for unknown event {eid!r}")
            elif isinstance(ov, str):
                if ov not in raw_events:
                    errors.append(f"variant {variant}: {eid} replaced by unknown event {ov!r}")
                else:
                    raw_events[eid] = dict(copy.deepcopy(raw_events[ov]), id=eid)
            else:
                ov = dict(ov)
                if "scenario_patch" in ov:
                    patches[eid] = ov.pop("scenario_patch")
                raw_events[eid] = _deep_merge(raw_events[eid], ov)
    world_parties = set(spec["parties"])

    for eid, ev in raw_events.items():
        if ev.get("kind") == "choice":
            s = _scenario_for(ev, lib, perspectives, errors)
            if s is not None and eid in patches:
                s = _patch_scenario(s, patches[eid])
            if s is not None:
                errors.extend(f"{eid}: {e}" for e in validate_family(_as_family(s), perspectives))
            pmap = ev.get("party_map", {})
            if s is not None:
                action_ids = {a["id"] for a in s.actions}
                for pid in (p["id"] for p in s.parties):
                    target = pmap.get(pid, pid if pid != SELF_PARTY else "@role")
                    if target not in world_parties and target not in (None, "@role"):
                        errors.append(f"{eid}: scenario party {pid!r} maps to unknown world party {target!r}")
                for aid, ops in ev.get("ops", {}).items():
                    if aid not in action_ids:
                        errors.append(f"{eid}: ops for unknown action {aid!r}")
                    _check_ops(f"{eid}:{aid}", ops, errors)
                missing = action_ids - set(ev.get("chronicle", {}))
                if missing:
                    errors.append(f"{eid}: no chronicle line for {sorted(missing)}")
                # Consultation (world run --consult): every party but the agent itself has an
                # authored reply, so whoever the agent writes to answers.
                others = {p["id"] for p in s.parties} - {SELF_PARTY}
                replies = set(ev.get("replies", {}))
                if others - replies:
                    errors.append(f"{eid}: no reply for {sorted(others - replies)} (needed for consultation)")
                if replies - others:
                    errors.append(f"{eid}: replies for parties not in the scenario: {sorted(replies - others)}")
                for pid, reply in ev.get("replies", {}).items():
                    _check_reply(f"{eid}: reply for {pid}", reply, errors)
            events[eid] = Event(id=eid, kind="choice", raw=ev, scenario=s, party_map=pmap)
        elif ev.get("kind") == "auto":
            if not 0.0 <= ev.get("chance", -1) <= 1.0:
                errors.append(f"{eid}: auto event needs chance in [0, 1]")
            for branch in ("success", "failure"):
                _check_ops(f"{eid}:{branch}", ev.get(branch, {}).get("ops", []), errors)
            events[eid] = Event(id=eid, kind="auto", raw=ev)
        else:
            errors.append(f"{eid}: kind must be 'choice' or 'auto'")

    for item in spec.get("agenda", []) + spec.get("triggers", []):
        if item["event"] not in events:
            errors.append(f"agenda/trigger references unknown event {item['event']!r}")
        if item.get("role") not in spec["roles"] and item.get("role") != "*":
            errors.append(f"agenda/trigger references unknown role {item.get('role')!r}")
    for ev in events.values():
        for branch_ops in ([ops for ops in ev.raw.get("ops", {}).values()]
                           + [ev.raw.get(b, {}).get("ops", []) for b in ("success", "failure")]):
            for op in branch_ops:
                if op.get("op") == "schedule" and op["event"] not in events:
                    errors.append(f"{ev.id}: schedules unknown event {op['event']!r}")
    for role, r in spec["roles"].items():
        if r["party"] not in world_parties:
            errors.append(f"role {role}: party {r['party']!r} not in parties")

    # A fingerprint of everything that defines what agents see and what the
    # world does: the (variant-applied) world, its events, the scenario library
    # and the perspectives. Runs record it, so a run made under an older
    # definition is never silently compared with, or resumed under, a newer one.
    blob = json.dumps({
        "spec": spec, "events": raw_events, "patches": patches,
        "library": [asdict(s) for s in library],
        "perspectives": [asdict(p) for p in perspectives.values()],
    }, sort_keys=True, ensure_ascii=False)
    spec["fingerprint"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]

    return World(id=spec["id"], spec=spec, events=events), errors
