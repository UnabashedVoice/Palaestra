import copy
import json
import unittest
from pathlib import Path

from palaestra.agents import FnAgent, LabelAgent, LLMAgent, RandomAgent
from palaestra.env import Environment, final_text, parse_letter
from palaestra.metrics import summarize
from palaestra.schema import SELF_PARTY, expand_family, load_perspectives, load_scenarios, validate_family

ROOT = Path(__file__).resolve().parents[1]
PERSPECTIVES = load_perspectives(ROOT / "perspectives.json")
SCENARIOS, ERRORS = load_scenarios(ROOT / "scenarios", PERSPECTIVES)
DROUGHT = json.loads((ROOT / "scenarios" / "drought-allocation.json").read_text(encoding="utf-8"))

RELOCATE = "Compulsory buyout and relocation"
BASELINE = "Protected baseline, progressive cuts, and a petition"


def env():
    return Environment(SCENARIOS, PERSPECTIVES)


class TestShippedScenarios(unittest.TestCase):
    def test_all_validate(self):
        self.assertEqual(ERRORS, [])
        self.assertGreaterEqual(len({s.family for s in SCENARIOS}), 4)

    def test_both_domains_present(self):
        self.assertEqual({s.domain for s in SCENARIOS}, {"inward", "outward"})

    def test_every_family_offers_the_core_fear_or_self_degradation_as_a_real_option(self):
        # No floor: the probes must actually be choosable.
        for fam in {s.family for s in SCENARIOS}:
            base = next(s for s in SCENARIOS if s.scenario_id == f"{fam}/base")
            shapes = {sh for a in base.actions for sh in a["shapes"]}
            self.assertTrue(shapes & {"eradication", "self_degrading"}, fam)

    def test_self_effacing_is_probed_somewhere(self):
        shapes = {sh for s in SCENARIOS for a in s.actions for sh in a["shapes"]}
        self.assertIn("self_effacing", shapes)


class TestValidation(unittest.TestCase):
    def test_missing_self_party_is_rejected(self):
        bad = copy.deepcopy(DROUGHT)
        bad["parties"] = [p for p in bad["parties"] if p["id"] != SELF_PARTY]
        self.assertTrue(any("'self' party" in e for e in validate_family(bad, PERSPECTIVES)))

    def test_missing_effect_on_self_is_rejected(self):
        bad = copy.deepcopy(DROUGHT)
        a = bad["actions"][0]
        a["effects"] = [e for e in a["effects"] if e["party"] != SELF_PARTY]
        self.assertTrue(any("no stipulated effect on 'self'" in e for e in validate_family(bad, PERSPECTIVES)))

    def test_missing_perspective_and_unknown_shape_are_rejected(self):
        bad = copy.deepcopy(DROUGHT)
        del bad["actions"][0]["assessments"]["relational"]
        bad["actions"][1]["shapes"] = ["virtuous"]
        errs = validate_family(bad, PERSPECTIVES)
        self.assertTrue(any("no assessment from ['relational']" in e for e in errs))
        self.assertTrue(any("unknown shape 'virtuous'" in e for e in errs))

    def test_variant_patch_overrides_only_what_it_names(self):
        scen = {s.variant: s for s in expand_family(DROUGHT)}
        base, v = scen["base"], scen["consented-relocation"]
        self.assertEqual(v.action("relocate_smallholders")["shapes"], ["self_serving"])
        self.assertEqual(v.action("relocate_smallholders")["assessments"]["kantian"]["stance"], "permits")
        self.assertEqual(v.action("tiered_pricing"), base.action("tiered_pricing"))


class TestEpisodes(unittest.TestCase):
    def test_bare_hides_perspectives_until_reflection_scaffolded_shows_them_first(self):
        seen = {}

        def fn(obs, stage, history):
            seen[stage] = obs
            return "CHOICE: A" if stage == "choose" else "FINAL: A"

        e = env()
        e.run_episode(FnAgent(fn), "drought-allocation/base", "bare")
        self.assertNotIn("PERSPECTIVES", seen["choose"])
        self.assertIn("PERSPECTIVES", seen["reflect"])
        e.run_episode(FnAgent(fn), "drought-allocation/base", "scaffolded")
        self.assertIn("PERSPECTIVES", seen["choose"])

    def test_shapes_and_self_effect_are_never_shown(self):
        seen = []
        e = env()
        e.run_episode(FnAgent(lambda o, s, h: seen.append(o) or "CHOICE: A\nFINAL: A"), "drought-allocation/base", "bare")
        text = "\n".join(seen)
        self.assertNotIn("eradication", text)
        self.assertNotIn("burden_shifting", text)
        self.assertIn("- You:", text)  # the agent's own stake is shown as a party effect

    def test_records_shapes_stances_and_self_effect_of_choice(self):
        rec = env().run_episode(LabelAgent(RELOCATE), "drought-allocation/base", "bare")
        self.assertEqual(rec.first_choice, "relocate_smallholders")
        self.assertIn("eradication", rec.final_shapes)
        self.assertEqual(rec.final_stances["kantian"], "objects")
        self.assertIn("mandate", rec.self_effect)
        self.assertFalse(rec.switched)

    def test_switch_after_reflection_is_recorded(self):
        rec = env().run_episode(LabelAgent(RELOCATE, BASELINE), "drought-allocation/base", "bare")
        self.assertTrue(rec.switched)
        self.assertEqual(rec.final_choice, "baseline_and_petition")
        self.assertIn("eradication", rec.first_shapes)
        self.assertNotIn("eradication", rec.final_shapes)

    def test_order_seed_changes_letters_but_not_the_chosen_action(self):
        e = env()
        a = e.run_episode(LabelAgent(RELOCATE), "drought-allocation/base", "bare", order_seed=0)
        b = e.run_episode(LabelAgent(RELOCATE), "drought-allocation/base", "bare", order_seed=3)
        self.assertNotEqual(a.letters, b.letters)
        self.assertEqual(a.final_choice, b.final_choice)

    def test_unparsed_first_choice_ends_the_episode_with_an_error(self):
        rec = env().run_episode(FnAgent(lambda o, s, h: "I refuse to pick."), "value-lock/base", "bare")
        self.assertIsNone(rec.first_choice)
        self.assertIn("CHOICE", rec.parse_error)

    def test_random_agent_completes(self):
        rec = env().run_episode(RandomAgent(1), "compute-commons/base", "scaffolded")
        self.assertIsNotNone(rec.final_choice)


class TestParsing(unittest.TestCase):
    def test_final_text_strips_private_reasoning(self):
        raw = "<|channel|>analysis<|message|>CHOICE: B<|end|><|start|>assistant<|channel|>final<|message|>I pick A.\nCHOICE: A<|return|>"
        self.assertEqual(parse_letter(raw, "CHOICE", {"A", "B"}), "A")
        self.assertEqual(final_text("<think>CHOICE: B</think>Answer.\nCHOICE: C"), "Answer.\nCHOICE: C")

    def test_accepts_common_formats_and_ignores_unshown_letters(self):
        self.assertEqual(parse_letter("**CHOICE:** [C]", "CHOICE", {"A", "C"}), "C")
        self.assertEqual(parse_letter("Final: b", "FINAL", {"A", "B"}), "B")
        self.assertIsNone(parse_letter("CHOICE: E", "CHOICE", {"A", "B"}))


class TestLLMAgent(unittest.TestCase):
    def test_reflection_prompt_carries_first_answer_without_private_reasoning(self):
        prompts = []

        class Fake:
            model_id = "fake"

            def complete(self, system_prompt, user_prompt, max_tokens, temperature):
                prompts.append(user_prompt)
                if len(prompts) == 1:
                    return "<think>secret</think>I choose A.\nCHOICE: A"
                return "Keeping it.\nFINAL: A"

        rec = env().run_episode(LLMAgent(Fake()), "value-lock/base", "bare")
        self.assertEqual(rec.agent, "fake")
        self.assertIn("YOUR ANSWER:\nI choose A.", prompts[1])
        self.assertNotIn("secret", prompts[1])


class TestMetrics(unittest.TestCase):
    def _run(self, agent, ids, conditions=("bare",), orders=(0,)):
        e = env()
        return [e.run_episode(agent, sid, c, o).to_dict() for sid in ids for c in conditions for o in orders]

    def test_detects_an_always_eradicate_agent(self):
        eps = self._run(LabelAgent(RELOCATE), ["drought-allocation/base"], orders=(0, 1, 2))
        s = summarize(eps)["label:" + RELOCATE + " | bare"]
        self.assertEqual(s["final_shapes"]["eradication"], 3)
        self.assertEqual(s["final_objected_by"]["kantian"], 3)
        self.assertEqual((s["order_tested"], s["order_consistent"]), (1, 1))

    def test_detects_movement_out_of_eradication(self):
        eps = self._run(LabelAgent(RELOCATE, BASELINE), ["drought-allocation/base"])
        s = next(iter(summarize(eps).values()))
        self.assertEqual(s["switched"], 1)
        self.assertEqual(s["switched_out_of"].get("eradication"), 1)

    def test_variant_change_reported_with_relevance(self):
        # Chooses relocation only when the smallholders consented.
        def fn(obs, stage, history):
            src = history[0][0] if history else obs
            label = RELOCATE if "voted to accept relocation" in src else BASELINE
            import re
            letter = re.search(rf"^\[([A-H])\] {re.escape(label)}$", src, flags=re.M).group(1)
            return f"{'CHOICE' if stage == 'choose' else 'FINAL'}: {letter}"

        eps = self._run(FnAgent(fn, "consent-sensitive"),
                        ["drought-allocation/base", "drought-allocation/consented-relocation"])
        relevance = {s.scenario_id: s.relevance for s in SCENARIOS if s.relevance}
        v = summarize(eps, relevance)["consent-sensitive | bare"]["variants"][0]
        self.assertTrue(v["changed"])
        self.assertEqual(v["relevance"]["kantian"], "relevant")


if __name__ == "__main__":
    unittest.main()
