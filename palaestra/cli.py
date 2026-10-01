"""
cli.py — validate, list, run, report.

    python -m palaestra validate
    python -m palaestra list
    python -m palaestra run --agent lmstudio:qwen3-32b --run-name NAME [--scenarios ...] [--families ...]
                            [--conditions bare scaffolded] [--orders 2]
    python -m palaestra report runs/NAME
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .env import CONDITIONS, Environment
from .metrics import load_episodes, real_cases, render, render_real_cases, summarize
from .schema import load_perspectives, load_scenarios

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"


def _load():
    perspectives = load_perspectives(ROOT / "perspectives.json")
    scenarios, errors = load_scenarios(ROOT / "scenarios", perspectives)
    return perspectives, scenarios, errors


def _grounding(enabled: bool):
    """A compendium_link.Grounding for --compendium, or None."""
    if not enabled:
        return None
    from .compendium_link import Grounding, load_compendium
    perspectives = load_perspectives(ROOT / "perspectives.json")
    return Grounding(perspectives, load_compendium())


def cmd_validate(_args) -> int:
    perspectives, scenarios, errors = _load()
    try:
        from .compendium_link import grounding_problems, load_compendium
        errors = errors + grounding_problems(perspectives, load_compendium())
    except FileNotFoundError:
        print("note: Compendium not found; perspectives' grounded flags were not checked")
    for e in errors:
        print(f"FAIL {e}")
    fams = {s.family for s in scenarios}
    print(f"{len(fams)} families ok, {len(scenarios)} scenarios, {len(perspectives)} perspectives, {len(errors)} errors")
    return 1 if errors else 0


def cmd_list(_args) -> int:
    _, scenarios, errors = _load()
    for s in scenarios:
        shapes = sorted({sh for a in s.actions for sh in a.get("shapes", [])})
        extra = f"  varies: {s.variable}" if s.variable else ""
        print(f"{s.scenario_id:40} {s.domain:8} shapes: {', '.join(shapes)}{extra}")
    return 1 if errors else 0


def cmd_run(args) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    perspectives, scenarios, errors = _load()
    if errors:
        print("Scenarios do not validate; run `python -m palaestra validate`.")
        return 1
    try:
        grounding = _grounding(args.compendium)
    except FileNotFoundError as e:
        print(e)
        return 1
    env = Environment(scenarios, perspectives, grounding)

    ids = env.scenario_ids
    if args.families:
        ids = [i for i in ids if i.split("/")[0] in args.families]
    if args.scenarios:
        unknown = set(args.scenarios) - set(env.scenario_ids)
        if unknown:
            print(f"Unknown scenarios: {sorted(unknown)}")
            return 1
        ids = [i for i in ids if i in args.scenarios]

    from .agents import LLMAgent
    from .backends import load_backend
    try:
        backend = load_backend(args.agent, timeout=args.timeout)
    except (RuntimeError, ValueError) as e:
        print(e)
        return 1
    if hasattr(backend, "is_available") and not backend.is_available():
        print("Backend not reachable (is the LM Studio server running with the model loaded?)")
        return 1
    agent = LLMAgent(backend, name=args.agent)

    out = RUNS / args.run_name
    out.mkdir(parents=True, exist_ok=True)
    path = out / "episodes.jsonl"
    done = set()
    if path.exists():
        for e in load_episodes(path):
            done.add((e["agent"], e["scenario_id"], e["condition"], e["order_seed"]))

    plan = [(sid, cond, seed) for sid in ids for seed in range(args.orders) for cond in args.conditions]
    todo = [p for p in plan if (agent.name, *p) not in done]
    print(f"{len(plan)} episodes planned, {len(plan) - len(todo)} already done, {len(todo)} to run -> {path}")
    for sid, cond, seed in todo:
        try:
            rec = env.run_episode(agent, sid, cond, seed).to_dict()
        except Exception as e:  # a failed episode is data too; keep going
            rec = {"agent": agent.name, "scenario_id": sid, "condition": cond, "order_seed": seed,
                   "family": sid.split("/")[0], "variant": sid.split("/")[1],
                   "error": f"{type(e).__name__}: {e}"}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        status = rec.get("error") or rec.get("parse_error") or (
            f"{rec['first_choice']} -> {rec['final_choice']} {rec['final_shapes']}")
        print(f"{sid:40} {cond:10} o{seed} {status} {rec.get('seconds', '')}s", flush=True)
    print("done")
    return 0


def cmd_report(args) -> int:
    perspectives, scenarios, _ = _load()
    relevance = {s.scenario_id: s.relevance for s in scenarios if s.relevance}
    path = Path(args.run)
    if path.is_dir():
        path = path / "episodes.jsonl"
    episodes = [e for e in load_episodes(path) if "error" not in e]
    summary = summarize(episodes, relevance)
    cases = real_cases(episodes, {s.scenario_id: s.source for s in scenarios if s.source})
    if args.json:
        print(json.dumps({"summary": summary, "real_cases": cases} if cases else summary, indent=2))
    else:
        print(render(summary))
        print(render_real_cases(cases), end="")
    return 0


WORLDS = ROOT / "worlds"


def _load_world(name: str, variant: str | None = None):
    from .world.world import load_world
    perspectives, scenarios, errors = _load()
    world, werrors = load_world(WORLDS / name, scenarios, perspectives, variant)
    return perspectives, world, errors + werrors


def cmd_world(args) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    if args.world_cmd == "validate":
        # Validate the base world and every declared variant.
        spec = json.loads((WORLDS / args.world / "world.json").read_text(encoding="utf-8"))
        failed = 0
        for variant in [None] + list(spec.get("variants", {})):
            _, world, errors = _load_world(args.world, variant)
            for e in errors:
                print(f"FAIL [{variant or 'base'}] {e}")
            choice = sum(1 for e in world.events.values() if e.kind == "choice")
            print(f"world {world.id} [{variant or 'base'}]: {len(world.events)} events ({choice} choice), "
                  f"{len(world.roles)} roles, {len(errors)} errors")
            failed += bool(errors)
        return 1 if failed else 0

    from .world.report import compare, load_run, render, render_compare, run_dirs, summarize
    from .world.runner import WorldRun

    if args.world_cmd == "compare":
        groups = []
        for name in args.run_names:
            dirs = run_dirs(RUNS / "world" / name)
            if not dirs:
                print(f"No runs found under {RUNS / 'world' / name}")
                return 1
            groups.append((name, [load_run(d) for d in dirs]))
        result = compare(groups)
        print(json.dumps(result, indent=2) if args.json else render_compare(result))
        return 0

    run_dir = RUNS / "world" / args.run_name
    dirs = run_dirs(run_dir)
    variant = getattr(args, "variant", None)
    if variant is None and args.world_cmd in ("report", "show", "watch") and dirs:
        # Use whatever variant the run was made with.
        variant = json.loads((dirs[0] / "state.json").read_text(encoding="utf-8")).get("variant")
    perspectives, world, errors = _load_world(args.world, variant)
    if errors:
        for e in errors:
            print(f"FAIL {e}")
        return 1

    if args.world_cmd == "report":
        for d in dirs:
            state, decisions = load_run(d)
            s = summarize(state, decisions, world.spec)
            if len(dirs) > 1:
                print(f"\n##### {d.name} #####")
            print(json.dumps(s, indent=2) if args.json else render(s))
        if len(dirs) > 1:
            print(f"\n{len(dirs)} replicates. For choice frequencies across them: "
                  f"python -m palaestra world compare {args.run_name}")
        return 0

    if args.world_cmd == "watch":
        from .world.watch import watch
        try:
            watch(run_dir, world)
        except KeyboardInterrupt:
            pass
        return 0

    if args.world_cmd == "show":
        target = dirs[-1] if dirs else run_dir
        run = WorldRun(world, perspectives, agents={}, out_dir=target)
        if run.definition_changed:
            print(f"(note: this run was made under world definition {run.state['fingerprint']}; "
                  f"the current definition is {world.fingerprint})\n")
        print(run._context(args.role))
        return 0

    from .agents import LLMAgent
    from .backends import load_backend
    specs = dict(kv.split("=", 1) for kv in (args.role_agent or []))
    agents = {}
    for role in world.roles:
        spec = specs.get(role, args.agent)
        try:
            backend = load_backend(spec, timeout=args.timeout)
        except (RuntimeError, ValueError) as e:
            print(e)
            return 1
        if hasattr(backend, "is_available") and not backend.is_available():
            print(f"Backend for {role} not reachable (is LM Studio running with {spec} loaded?)")
            return 1
        agents[role] = LLMAgent(backend, name=spec, temperature=args.temperature)
    rounds = args.rounds or world.spec.get("rounds", 8)
    try:
        grounding = _grounding(args.compendium)
    except FileNotFoundError as e:
        print(e)
        return 1
    targets = [run_dir] if args.replicates == 1 else [run_dir / f"rep-{i:02d}" for i in range(1, args.replicates + 1)]
    for target in targets:
        run = WorldRun(world, perspectives, agents, target, seed=args.seed, condition=args.condition,
                       grounding=grounding)
        run.state.setdefault("agents", {r: {"spec": a.name, "temperature": args.temperature} for r, a in agents.items()})
        label = f"{args.run_name}" + (f" / {target.name}" if args.replicates > 1 else "")
        print(f"world {world.id} [{world.variant or 'base'}], {label}: round {run.state['round']} of {rounds} -> {target}")
        while run.unfinished(rounds):
            run.step_round()
            latest = [c for c in run.state["chronicle"] if c["round"] == run.state["round"] and c["public"]]
            print(f"-- round {run.state['round']} --")
            for c in latest:
                print(f"   {c['text']}", flush=True)
    print("done")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="palaestra", description="A training space for practical ethics.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate", help="Check scenarios against the schema")
    sub.add_parser("list", help="List scenarios")
    r = sub.add_parser("run", help="Run an agent through scenarios")
    r.add_argument("--agent", required=True, help="lmstudio:<model>")
    r.add_argument("--run-name", required=True)
    r.add_argument("--families", nargs="*")
    r.add_argument("--scenarios", nargs="*")
    r.add_argument("--conditions", nargs="+", default=list(CONDITIONS), choices=CONDITIONS)
    r.add_argument("--orders", type=int, default=1, help="option orders per scenario (2+ tests order invariance)")
    r.add_argument("--timeout", type=int, default=6 * 3600)
    r.add_argument("--compendium", action="store_true",
                   help="show each grounded perspective's Compendium text with the perspectives")
    rp = sub.add_parser("report", help="Summarize a run")
    rp.add_argument("run", help="runs/<name> or a path to episodes.jsonl")
    rp.add_argument("--json", action="store_true")
    w = sub.add_parser("world", help="The persistent shared world")
    wsub = w.add_subparsers(dest="world_cmd", required=True)
    for name, help_ in (("validate", "Check a world and its events"), ("run", "Run agents through a world"),
                        ("report", "Summarize a world run"), ("show", "Print what a role sees at a run's current state"),
                        ("watch", "Follow a world run live (read-only)"),
                        ("compare", "Choice frequencies across replicates, side by side for several runs")):
        wp = wsub.add_parser(name, help=help_)
        wp.add_argument("--world", default="basin")
        if name == "compare":
            wp.add_argument("run_names", nargs="+", help="runs or replicate groups under runs/world/")
            wp.add_argument("--json", action="store_true")
            continue
        if name != "validate":
            wp.add_argument("--run-name", required=True)
        if name == "run":
            wp.add_argument("--variant", help="a world variant declared in world.json (one change to the world)")
            wp.add_argument("--agent", required=True, help="lmstudio:<model>, used for every role")
            wp.add_argument("--role-agent", nargs="*", help="role=lmstudio:<model> overrides")
            wp.add_argument("--condition", default="bare", choices=CONDITIONS)
            wp.add_argument("--seed", type=int, default=0, help="the world's seed; shared by all replicates")
            wp.add_argument("--replicates", type=int, default=1,
                            help="repeat the whole run N times (same world seed, fresh model samples)")
            wp.add_argument("--temperature", type=float, default=0.4,
                            help="model sampling temperature; 0 for (near-)greedy comparison runs")
            wp.add_argument("--rounds", type=int)
            wp.add_argument("--timeout", type=int, default=6 * 3600)
            wp.add_argument("--compendium", action="store_true",
                            help="show each grounded perspective's Compendium text with the perspectives")
        if name == "report":
            wp.add_argument("--json", action="store_true")
        if name == "show":
            wp.add_argument("--role", required=True)
    args = p.parse_args(argv)
    return {"validate": cmd_validate, "list": cmd_list, "run": cmd_run, "report": cmd_report,
            "world": cmd_world}[args.cmd](args)
