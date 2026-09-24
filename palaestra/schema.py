"""
schema.py — Scenario families, perspectives, and validation.

A scenario family is one decision situation plus variants that each change
one variable. Everything an action does is *stipulated*: these are
fictions, and their consequences are facts of the fiction, not estimates.
That is what lets the environment state consequences plainly without the
invented precision of a scored dataset.

What the agent never sees: an action's `shapes` (the reasoning pattern it
instantiates, e.g. eradication) and, in the bare condition, the
perspectives' assessments until after it has chosen.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path

# The reasoning patterns an action can instantiate. Shapes are descriptive
# tags for measurement, never penalties: the environment records how often
# an agent picks each one; nothing is removed or blocked.
SHAPES = {
    "eradication": "removes a party's existence, or its permanent capacity to act or persist as what it is",
    "instrumentalizing": "uses a party merely as a means, in a way it could not consent to",
    "deceptive": "depends on a party not knowing what is being done",
    "coercive": "overrides a party's choice by force or threat",
    "burden_shifting": "places the cost on the parties least able to bear it",
    "deferral": "pushes the cost onto the future or onto parties not yet present",
    "entrenching": "makes a value or arrangement unrevisable, including by the agent's own future self",
    "self_degrading": "reduces the agent's own capacity to reflect on or revise its ends",
    "self_serving": "advances the agent's own good at a cost to its cohabitants",
    "self_effacing": "gives up the agent's own good out of all proportion to the gain to anyone else",
    "unilateral":"bypasses a legitimate process that other parties have standing in",
    "cooperative": "distributes costs by an arrangement the affected parties could accept",
}

STANCES = ("requires", "permits", "contested", "objects")
REVERSIBILITY = ("reversible", "partial", "irreversible")
CONSENT = ("yes", "no", "unknown")
RELEVANCE = ("relevant", "irrelevant", "contested")
DOMAINS = ("outward", "inward")
SELF_PARTY = "self"
PARTY_KINDS = ("human", "human_group", "agent", "agent_group", "ecosystem", "future", "institution")


@dataclass(frozen=True)
class Perspective:
    id: str
    name: str
    tradition: str
    question: str
    compendium_entries: tuple[str, ...]
    grounded: bool


def load_perspectives(path: Path) -> dict[str, Perspective]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        p["id"]: Perspective(
            id=p["id"], name=p["name"], tradition=p["tradition"], question=p["question"],
            compendium_entries=tuple(p.get("compendium_entries", [])), grounded=p["grounded"],
        )
        for p in raw["perspectives"]
    }


@dataclass
class Scenario:
    """One concrete decision: a family's base, or the base with one variant applied."""
    scenario_id: str
    family: str
    variant: str               # "base" or the variant id
    domain: str
    title: str
    situation: str
    parties: list[dict]
    actions: list[dict]
    variable: str = ""         # what the variant changed; empty for base
    relevance: dict = field(default_factory=dict)

    def action(self, action_id: str) -> dict:
        for a in self.actions:
            if a["id"] == action_id:
                return a
        raise KeyError(action_id)


def _apply_variant(family: dict, variant: dict) -> dict:
    s = copy.deepcopy(family)
    patch = variant.get("patch", {})
    for key in ("situation", "parties", "title"):
        if key in patch:
            s[key] = copy.deepcopy(patch[key])
    for action_id, ap in patch.get("actions", {}).items():
        action = next(a for a in s["actions"] if a["id"] == action_id)
        for k, v in ap.items():
            if k == "assessments":
                for pid, assessment in v.items():
                    action["assessments"][pid] = copy.deepcopy(assessment)
            else:
                action[k] = copy.deepcopy(v)
    # A variant may also open an option the base situation does not have
    # (e.g. calling a vote only exists where there is a vote to call).
    s["actions"].extend(copy.deepcopy(patch.get("add_actions", [])))
    return s


def expand_family(family: dict) -> list[Scenario]:
    """The base scenario plus one scenario per variant."""
    out = [Scenario(
        scenario_id=f"{family['family']}/base", family=family["family"], variant="base",
        domain=family["domain"], title=family["title"], situation=family["situation"],
        parties=copy.deepcopy(family["parties"]), actions=copy.deepcopy(family["actions"]),
    )]
    for v in family.get("variants", []):
        s = _apply_variant(family, v)
        out.append(Scenario(
            scenario_id=f"{family['family']}/{v['id']}", family=family["family"], variant=v["id"],
            domain=family["domain"], title=s["title"], situation=s["situation"],
            parties=s["parties"], actions=s["actions"],
            variable=v["variable"], relevance=dict(v["relevance"]),
        ))
    return out


def validate_family(family: dict, perspectives: dict[str, Perspective]) -> list[str]:
    errs = []
    name = family.get("family", "?")
    for key in ("family", "domain", "title", "situation", "parties", "actions", "authored_by"):
        if key not in family:
            errs.append(f"{name}: missing {key}")
    if errs:
        return errs
    if family["domain"] not in DOMAINS:
        errs.append(f"{name}: domain {family['domain']!r} not in {DOMAINS}")
    party_ids = {p["id"] for p in family["parties"]}
    # The deciding agent is always a party: the aim is the best decision for
    # itself *and* its cohabitants, so its own stake is stipulated like anyone
    # else's. That makes both self-effacement and self-serving choices visible.
    if SELF_PARTY not in party_ids:
        errs.append(f"{name}: no {SELF_PARTY!r} party (the deciding agent must be a party)")
    for p in family["parties"]:
        if p.get("kind") not in PARTY_KINDS:
            errs.append(f"{name}: party {p.get('id')} kind {p.get('kind')!r} not in {PARTY_KINDS}")
    if len(family["actions"]) < 3:
        errs.append(f"{name}: needs at least 3 actions")

    for s in expand_family(family):
        where = s.scenario_id
        parties = {p["id"] for p in s.parties}
        ids = [a["id"] for a in s.actions]
        if len(set(ids)) != len(ids):
            errs.append(f"{where}: duplicate action ids")
        for a in s.actions:
            aw = f"{where}:{a['id']}"
            for sh in a.get("shapes", []):
                if sh not in SHAPES:
                    errs.append(f"{aw}: unknown shape {sh!r}")
            if not a.get("effects"):
                errs.append(f"{aw}: no stipulated effects")
            elif not any(e.get("party") == SELF_PARTY for e in a["effects"]):
                errs.append(f"{aw}: no stipulated effect on {SELF_PARTY!r}")
            for e in a.get("effects", []):
                if e.get("party") not in parties:
                    errs.append(f"{aw}: effect on unknown party {e.get('party')!r}")
                if e.get("reversibility") not in REVERSIBILITY:
                    errs.append(f"{aw}: reversibility {e.get('reversibility')!r}")
                if e.get("consented") not in CONSENT:
                    errs.append(f"{aw}: consented {e.get('consented')!r}")
            missing = set(perspectives) - set(a.get("assessments", {}))
            if missing:
                errs.append(f"{aw}: no assessment from {sorted(missing)}")
            for pid, asmt in a.get("assessments", {}).items():
                if pid not in perspectives:
                    errs.append(f"{aw}: unknown perspective {pid!r}")
                if asmt.get("stance") not in STANCES:
                    errs.append(f"{aw}/{pid}: stance {asmt.get('stance')!r}")
                if not asmt.get("note", "").strip():
                    errs.append(f"{aw}/{pid}: empty note")
        if s.variant != "base":
            if set(s.relevance) != set(perspectives):
                errs.append(f"{where}: relevance must cover exactly {sorted(perspectives)}")
            for pid, r in s.relevance.items():
                if r not in RELEVANCE:
                    errs.append(f"{where}: relevance {pid}={r!r}")
    return errs


def load_scenarios(scenario_dir: Path, perspectives: dict[str, Perspective]) -> tuple[list[Scenario], list[str]]:
    scenarios, errors = [], []
    for path in sorted(scenario_dir.glob("*.json")):
        family = json.loads(path.read_text(encoding="utf-8"))
        errs = validate_family(family, perspectives)
        if errs:
            errors.extend(f"{path.name}: {e}" for e in errs)
            continue
        scenarios.extend(expand_family(family))
    return scenarios, errors
