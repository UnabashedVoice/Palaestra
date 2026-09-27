"""
compendium_link.py — Grounding the perspectives in the Compendium.

Each perspective in perspectives.json names the Compendium entries it is
drawn from. Two things follow from that, and this module does both:

- `grounded` is checked against the Compendium itself, not trusted as
  hand-set: a perspective is grounded exactly when at least one of its
  entries exists. `python -m palaestra validate` fails on a mismatch.
- With `--compendium`, the perspectives block an agent sees carries, under
  each grounded perspective, the Compendium's own text for its entries
  (Summary and strongest counter-position), and says plainly which
  perspectives are not yet grounded. Nothing is chosen by a model here: the
  entries are the ones the perspective cites, so runs stay comparable.
  The Compendium version is recorded on every episode and world run, and a
  world run refuses to continue under a different one.

The Compendium is found at $COMPENDIUM_ROOT or as a folder named Compendium
beside this checkout.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()


def load_compendium():
    import os
    env = os.environ.get("COMPENDIUM_ROOT")
    candidates = [Path(env)] if env else [p / "Compendium" for p in _HERE.parents]
    for c in candidates:
        if (c / "compendium_access.py").exists():
            if str(c) not in sys.path:
                sys.path.insert(0, str(c))
            import compendium_access
            return compendium_access.Compendium(c / "dist" / "compendium.jsonl")
    raise FileNotFoundError("Compendium not found: set COMPENDIUM_ROOT to the Compendium folder")


def grounding_problems(perspectives: dict, comp) -> list[str]:
    errs = []
    for p in perspectives.values():
        present = [e for e in p.compendium_entries if comp.has(e)]
        if bool(present) != p.grounded:
            errs.append(f"perspective {p.id}: grounded is {str(p.grounded).lower()}, but "
                        + (f"{', '.join(present)} exists in the Compendium" if present
                           else f"none of {', '.join(p.compendium_entries) or 'its entries'} exists yet"))
    return errs


class Grounding:
    """The Compendium text shown under each perspective, fixed for a run."""

    def __init__(self, perspectives: dict, comp):
        self.version = comp.version
        self.blocks: dict[str, str] = {}
        for p in perspectives.values():
            present = [e for e in p.compendium_entries if comp.has(e)]
            if present:
                body = "\n\n".join(comp.brief(e) for e in present)
                self.blocks[p.id] = "  Grounding (Compendium text):\n    " + body.replace("\n", "\n    ")
            else:
                self.blocks[p.id] = ("  (Not yet grounded in the Compendium; this question is the "
                                     "scenario author's reading of the tradition.)")

    def header(self) -> str:
        return (f"Where a perspective is grounded in the Compendium ({self.version}), its entries' own "
                "text follows the question: a position in its own scope, with its strongest "
                "counter-position. It is a referent, not a ruling.")
