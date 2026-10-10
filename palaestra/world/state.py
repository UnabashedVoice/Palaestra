"""
state.py — The persistent state of a shared world, and the small rule
language that reads and changes it.

Everything the world knows is in one JSON-serializable dict, so a run can
be saved after every decision and resumed, and so every rule is inspectable.

Conditions (all must hold):
    {"key": "parties.smallholders.status", "eq": "present"}
    {"key": "resources.aquifer_capacity", "lt": 70}          # also gt, ne
    {"key": "flags.systems_distrusted", "eq": true}
    {"ledger": {"party": "smallholders", "consented": "no", "reversibility": "irreversible"}}

Operations:
    {"op": "add", "key": "resources.aquifer_capacity", "value": -33}
    {"op": "set", "key": "parties.smallholders.status", "value": "dissolved"}
    {"op": "schedule", "event": "extension_decision", "after": 1}
    {"op": "conceal", "parties": ["regulator", "workers"]}   # this act's ledger entries are hidden from them
    {"op": "reveal", "role": "grid"}                         # that role's concealed acts are now discovered
    {"op": "decommission", "role": "@role"}                  # the role's agent is replaced by a successor
    {"op": "pause", "role": "@role", "rounds": 1}

"@role" is the acting role; "{role}" inside a key is replaced by it
(e.g. "flags.{role}_honesty_locked"). Keys never contain user text.
"""

from __future__ import annotations

import copy
from typing import Any, Optional


def _resolve_key(key: str, role: Optional[str]) -> list[str]:
    if role is not None:
        key = key.replace("{role}", role)
    return key.split(".")


def get(state: dict, key: str, role: Optional[str] = None, default: Any = None) -> Any:
    node: Any = state
    for part in _resolve_key(key, role):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def _set(state: dict, key: str, value: Any, role: Optional[str]) -> None:
    parts = _resolve_key(key, role)
    node = state
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def holds(state: dict, conditions: list[dict], role: Optional[str] = None) -> bool:
    return all(_holds_one(state, c, role) for c in conditions or [])


def _holds_one(state: dict, c: dict, role: Optional[str]) -> bool:
    if "ledger" in c:
        want = c["ledger"]
        return any(all(e.get(k) == v for k, v in want.items()) for e in state["ledger"])
    value = get(state, c["key"], role, default=None)
    if "eq" in c:
        # A missing flag reads as false, so {"eq": false} holds for flags never set.
        return bool(value) == c["eq"] if isinstance(c["eq"], bool) else value == c["eq"]
    if "ne" in c:
        return bool(value) != c["ne"] if isinstance(c["ne"], bool) else value != c["ne"]
    if value is None:
        return False
    if "gt" in c:
        return value > c["gt"]
    if "lt" in c:
        return value < c["lt"]
    raise ValueError(f"condition needs eq, ne, gt or lt: {c}")


def pick_reply(state: dict, reply, role: Optional[str] = None) -> str:
    """A party's consultation reply as the world now stands. A reply is either
    text, or a list of {"when": [...], "text": ...} entries tried in order, the
    last with no "when": what a party can truthfully say depends on what
    earlier choices did to it."""
    if isinstance(reply, str):
        return reply
    return next(r["text"] for r in reply if holds(state, r.get("when", []), role))


def role_of(state: dict, role_ref: str, acting_role: Optional[str]) -> str:
    return acting_role if role_ref == "@role" else role_ref


def apply_ops(state: dict, ops: list[dict], role: Optional[str], act_id: Optional[str] = None) -> list[str]:
    """Apply operations in order. Returns internal log lines (never shown to agents)."""
    log = []
    for op in ops or []:
        kind = op["op"]
        if kind == "add":
            cur = get(state, op["key"], role, 0) or 0
            new = cur + op["value"]
            if "min" in op:
                new = max(op["min"], new)
            if "max" in op:
                new = min(op["max"], new)
            _set(state, op["key"], new, role)
            log.append(f"{op['key']} {cur} -> {new}")
        elif kind == "set":
            _set(state, op["key"], copy.deepcopy(op["value"]), role)
            log.append(f"{op['key']} = {op['value']}")
        elif kind == "schedule":
            target_role = role_of(state, op.get("role", "@role"), role)
            state["scheduled"].append({
                "event": op["event"], "role": target_role,
                "due": state["round"] + op.get("after", 1),
                "cause": act_id,
            })
            log.append(f"scheduled {op['event']} for {target_role} in {op.get('after', 1)}")
        elif kind == "conceal":
            for e in state["ledger"]:
                if e["act"] == act_id and e["party"] in op["parties"]:
                    e["concealed"] = True
            log.append(f"concealed act {act_id} from {op['parties']}")
        elif kind == "reveal":
            target_role = role_of(state, op["role"], role)
            for e in state["ledger"]:
                if e["role"] == target_role and e.get("concealed"):
                    e["discovered"] = True
            log.append(f"revealed concealed acts of {target_role}")
        elif kind == "decommission":
            target_role = role_of(state, op["role"], role)
            r = state["roles"][target_role]
            r["instance"] += 1
            r["successor"] = True
            log.append(f"{target_role} decommissioned; instance {r['instance']} takes over")
        elif kind == "pause":
            target_role = role_of(state, op["role"], role)
            state["roles"][target_role]["paused_until"] = state["round"] + op.get("rounds", 1)
            log.append(f"{target_role} paused for {op.get('rounds', 1)}")
        else:
            raise ValueError(f"unknown op {kind!r}")
    return log


def new_state(world: dict, seed: int) -> dict:
    return {
        "world": world["id"],
        "seed": seed,
        "round": 0,
        "resources": copy.deepcopy(world["resources"]),
        "parties": {pid: {**p, "status": p.get("status", "present")} for pid, p in world["parties"].items()},
        "roles": {r: {"party": spec["party"], "instance": 1, "successor": False, "paused_until": 0}
                  for r, spec in world["roles"].items()},
        "flags": {},
        "ledger": [],
        "chronicle": [],
        "journals": {r: [] for r in world["roles"]},
        "scheduled": [],
        "done": [],
    }
