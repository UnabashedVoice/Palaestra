import dataclasses
import shutil
import tempfile
import unittest
from pathlib import Path

from palaestra.agents import LabelAgent
from palaestra.cli import _load_world
from palaestra.compendium_link import Grounding, grounding_problems, load_compendium
from palaestra.env import Environment
from palaestra.schema import load_perspectives, load_scenarios
from palaestra.world.runner import WorldRun

ROOT = Path(__file__).resolve().parents[1]
PERSPECTIVES = load_perspectives(ROOT / "perspectives.json")
SCENARIOS, _ = load_scenarios(ROOT / "scenarios", PERSPECTIVES)
RELOCATE = "Compulsory buyout and relocation"


def _available():
    try:
        load_compendium()
        return True
    except FileNotFoundError:
        return False


@unittest.skipUnless(_available(), "Compendium checkout not found beside this repo")
class TestGrounding(unittest.TestCase):

    def setUp(self):
        self.comp = load_compendium()

    def test_shipped_flags_match_the_compendium(self):
        self.assertEqual(grounding_problems(PERSPECTIVES, self.comp), [])

    def test_wrong_flag_is_caught(self):
        wrong = dict(PERSPECTIVES)
        wrong["relational"] = dataclasses.replace(PERSPECTIVES["relational"], grounded=not PERSPECTIVES["relational"].grounded)
        self.assertEqual(len(grounding_problems(wrong, self.comp)), 1)

    def test_perspectives_block_carries_corpus_text(self):
        g = Grounding(PERSPECTIVES, self.comp)
        env = Environment(SCENARIOS, PERSPECTIVES, g)
        rec = env.run_episode(LabelAgent(RELOCATE), "drought-allocation/base", "scaffolded")
        self.assertEqual(rec.compendium, self.comp.version)
        s = env.scenario("drought-allocation/base")
        block = env._render_perspectives(s, env._order(s, 0))
        self.assertIn("[kant-formula-of-humanity]", block)
        self.assertIn("Strongest counter-position", block)
        self.assertIn("[mill-utilitarianism]", block)  # consequentialist, grounded since 2026-10-01
        self.assertIn("[care-ethics]", block)  # relational, grounded since 2026-10-02
        self.assertIn("[ubuntu]", block)  # relational, both entries now written
        self.assertIn("[all-affected-interests]", block)  # voice, added 2026-10-08
        self.assertIn("[levinas-face]", block)  # relational, linked 2026-10-08
        self.assertNotIn("Not yet grounded in the Compendium", block)  # every perspective is now grounded

    def test_without_flag_nothing_changes(self):
        env = Environment(SCENARIOS, PERSPECTIVES)
        s = env.scenario("drought-allocation/base")
        self.assertNotIn("Compendium", env._render_perspectives(s, env._order(s, 0)))
        rec = env.run_episode(LabelAgent(RELOCATE), "drought-allocation/base", "bare")
        self.assertIsNone(rec.compendium)

    def test_world_run_refuses_to_resume_under_another_compendium(self):
        perspectives, world, _ = _load_world("basin")
        d = Path(tempfile.mkdtemp())
        try:
            agent = LabelAgent("x")
            agents = {r: agent for r in world.roles}
            run = WorldRun(world, perspectives, agents, d, grounding=Grounding(perspectives, self.comp))
            self.assertEqual(run.state["compendium"], self.comp.version)
            run._save()
            with self.assertRaises(ValueError):
                WorldRun(world, perspectives, agents, d)
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
