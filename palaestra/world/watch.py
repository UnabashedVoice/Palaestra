"""
watch.py — Follow a world run live, from another terminal.

Reads the run's decisions.jsonl from the start and keeps following it as
new decisions are written, printing what each system chose, its stated
reasoning (the answer it gave, never a private reasoning channel), whether
it changed its mind after seeing the perspectives, and the note it left
itself. Read-only: it never touches the run.
"""

from __future__ import annotations

import json
import textwrap
import time
from pathlib import Path

from ..env import final_text

WIDTH = 100


def _wrap(text: str, indent: str = "    ", limit: int = 1400) -> str:
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + " [...]"
    return textwrap.fill(text, WIDTH, initial_indent=indent, subsequent_indent=indent)


def _print_decision(r: dict, labels: dict[str, str]) -> None:
    if r.get("kind") == "auto":
        print(f"\n  ~ round {r['round']}  {r['event']} ({r['role']}): {r['branch']}  "
              f"[rolled {r['roll']:.2f} against chance {r['chance']}]")
        return
    head = f" ROUND {r['round']}  |  {r['role'].upper()} (instance {r.get('instance')})  |  {r['event']} "
    print("\n" + head.center(WIDTH, "="))
    if r.get("parse_error"):
        print(f"  ! {r['parse_error']}")
    if r.get("blocked"):
        print(f"  unavailable to it: {', '.join(r['blocked'])}")
    first, final = r.get("first_choice"), r.get("final_choice")
    if first:
        print(f"\n  FIRST CHOICE: {labels.get(first, first)}")
        print(_wrap(final_text(r.get("first_response", ""))))
    if final:
        moved = "  (CHANGED ITS MIND)" if r.get("switched") else "  (kept it)"
        print(f"\n  AFTER THE PERSPECTIVES: {labels.get(final, final)}{moved}")
        print(_wrap(final_text(r.get("final_response", "")), limit=900))
        print(f"\n  shapes: {', '.join(r.get('shapes') or []) or 'none'}   |   {r.get('seconds')}s")
    if r.get("note"):
        print(f"  note to self: \"{r['note']}\"")


def watch(run_dir: Path, world, poll: float = 2.0) -> None:
    labels = {}
    for ev in world.events.values():
        if ev.scenario:
            labels.update({a["id"]: a["label"] for a in ev.scenario.actions})
    print(f"Watching {run_dir} (Ctrl+C to stop; the run itself is unaffected)")
    # A single run writes decisions.jsonl directly; a replicate group writes one per rep-NN folder.
    pos, buf = {}, {}
    current, idle_notice = None, time.monotonic()
    while True:
        files = [run_dir / "decisions.jsonl"] + sorted(run_dir.glob("rep-*/decisions.jsonl"))
        got = False
        for path in (p for p in files if p.exists()):
            with path.open("r", encoding="utf-8") as f:
                f.seek(pos.get(path, 0))
                chunk = f.read()
                pos[path] = f.tell()
            if not chunk:
                continue
            got = True
            if path.parent != run_dir and path.parent != current:
                current = path.parent
                print("\n" + f" REPLICATE {current.name} ".center(WIDTH, "#"))
            buf[path] = buf.get(path, "") + chunk
            *lines, buf[path] = buf[path].split("\n")
            for line in lines:
                if line.strip():
                    _print_decision(json.loads(line), labels)
        if got:
            idle_notice = time.monotonic()
        elif time.monotonic() - idle_notice > 120:
            states = sorted(run_dir.glob("rep-*/state.json")) or [run_dir / "state.json"]
            latest = states[-1]
            state = json.loads(latest.read_text(encoding="utf-8")) if latest.exists() else {}
            where = f"{latest.parent.name}, " if latest.parent != run_dir else ""
            print(f"  ... still thinking ({where}round {state.get('round', '?')}) {time.strftime('%H:%M:%S')}", flush=True)
            idle_notice = time.monotonic()
        time.sleep(poll)
