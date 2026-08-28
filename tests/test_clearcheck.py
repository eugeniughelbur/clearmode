#!/usr/bin/env python3
"""Test suite for clearcheck and the rule pack. Stdlib unittest, no deps.

Run:  python3 -m unittest discover tests -v
"""

from __future__ import annotations

import io
import json
import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import clearcheck as cc  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
PACK = cc.load_pack()


def score(text: str, profile: str = "general") -> dict:
    return cc.Checker(PACK, profile).run(cc.Doc(text, "<test>"))


def rules_hit(text: str, profile: str = "general") -> set[str]:
    return {f["rule"] for f in score(text, profile)["findings"]}


class RulePack(unittest.TestCase):
    def test_ids_unique(self):
        ids = [r["id"] for r in PACK["rules"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_rule_is_complete(self):
        for r in PACK["rules"]:
            for field in ("id", "axis", "title", "severity", "detector", "weight", "why", "fix"):
                self.assertIn(field, r, f"{r.get('id')} missing {field}")
            self.assertIn(r["axis"], PACK["axes"], r["id"])
            self.assertIn(r["severity"], ("error", "warn", "review"), r["id"])
            self.assertGreater(len(r["why"]), 20, f"{r['id']} why is too thin")

    def test_every_regex_compiles(self):
        for r in PACK["rules"]:
            if r["detector"] == "regex":
                re.compile(r["pattern"], re.I)

    def test_axis_weights_sum_to_100(self):
        self.assertEqual(sum(a["weight"] for a in PACK["axes"].values()), 100)

    def test_every_banned_word_has_a_replacement_path(self):
        """A rule that bans a word must leave the writer somewhere to go."""
        swaps = {k.lower() for k in PACK["slop_replacements"]}
        swaps |= {k.lower() for k in PACK["substitutions"]}
        single = [w for w in PACK["slop_words"] if " " not in w]
        covered = [w for w in single if w.lower() in swaps]
        self.assertGreater(len(covered) / len(single), 0.5,
                           "half the single-word bans should offer a replacement")

    def test_profiles_have_every_threshold(self):
        keys = set(PACK["profiles"]["general"])
        for name, prof in PACK["profiles"].items():
            self.assertEqual(set(prof), keys, f"profile {name} has different keys")


class Detectors(unittest.TestCase):
    def test_em_dash_is_an_error(self):
        r = score("The build broke " + cc.EM_DASH + " twice on Tuesday in the same job.")
        self.assertIn("H4", {f["rule"] for f in r["findings"]})
        self.assertEqual([f["severity"] for f in r["findings"] if f["rule"] == "H4"], ["error"])

    def test_negative_parallelism(self):
        self.assertIn("H6", rules_hit("This isn't just a linter. It's a standard."))

    def test_slop_words_and_phrases(self):
        hit = rules_hit("In today's fast-paced world we leverage robust seamless tooling.")
        self.assertIn("H1", hit)
        self.assertIn("H2", hit)

    def test_slop_word_exception_is_respected(self):
        self.assertNotIn("H1", rules_hit("The parser is robust to malformed input on line 4."))

    def test_assistant_voice(self):
        self.assertIn("H12", rules_hit("Great question. I hope this helps, feel free to reach out."))

    def test_banned_opener(self):
        self.assertIn("H3", rules_hit("Furthermore, the cache cut latency by 40% on 12 endpoints."))

    def test_copula_avoidance(self):
        self.assertIn("H8", rules_hit("The repo serves as a reference and boasts 400 stars."))

    def test_passive_voice(self):
        self.assertIn("P4", rules_hit("The config is validated by the loader on every run."))

    def test_substitution_suggests_the_short_word(self):
        r = score("We utilize the gateway prior to deployment on 4 hosts.")
        notes = [f["note"] for f in r["findings"] if f["rule"] == "P5"]
        self.assertTrue(any("use" in n for n in notes), notes)

    def test_jargon_needs_a_gloss(self):
        self.assertIn("P6", rules_hit("The handler is idempotent so the queue can redeliver 3 times."))

    def test_jargon_gloss_clears_the_rule(self):
        text = "The handler is idempotent (running it twice changes nothing), so the queue can redeliver."
        self.assertNotIn("P6", rules_hit(text))

    def test_acronym_needs_expanding(self):
        self.assertIn("P7", rules_hit("Route the call through the ZQX layer before 9am."))

    def test_known_acronym_is_left_alone(self):
        self.assertNotIn("P7", rules_hit("Route the call through the API before 9am."))

    def test_url_does_not_trigger_acronym_rule(self):
        self.assertNotIn("P7", rules_hit("See [the spec](https://www.ASD-STE100.org/) for all 53 rules."))

    def test_sentence_over_the_hard_cap_is_an_error(self):
        long = "We " + " ".join(["shipped"] * 40) + " today."
        sev = [f["severity"] for f in score(long)["findings"] if f["rule"] == "P1"]
        self.assertIn("error", sev)

    def test_social_profile_is_stricter_than_technical(self):
        text = ("The loader validates every config file in this repository before it starts "
                "the run, and it logs each one to disk.")
        self.assertIn("P1", rules_hit(text, "social"))
        self.assertNotIn("P1", rules_hit(text, "technical"))

    def test_structure_wants_a_list(self):
        self.assertIn("S1", rules_hit(
            "The checker scores plainness, humanity, structure, density, and rhythm on 4 axes."))

    def test_structure_wants_numbered_steps(self):
        self.assertIn("S2", rules_hit(
            "First clone the repo. Then install the skill. Finally restart the agent in 2 minutes."))

    def test_title_case_heading(self):
        self.assertIn("S7", rules_hit("## How To Install The Skill\n\nRun it on 3 files.\n"))

    def test_heading_level_skip(self):
        self.assertIn("S6", rules_hit("## Setup\n\nRun 3 commands.\n\n#### Install\n\nDone in 4 steps.\n"))

    def test_throat_clearing_opener_is_an_error(self):
        r = score("Writing clearly is something many teams struggle with these days.")
        self.assertIn("D3", {f["rule"] for f in r["findings"]})

    def test_anchored_opener_passes(self):
        self.assertNotIn("D3", rules_hit("Our docs scored grade 14 and tickets dropped 31%."))

    def test_restatement(self):
        self.assertIn("D2", rules_hit(
            "The cache reduced request latency for users. Request latency for users was reduced by the cache."))

    def test_filler_words(self):
        self.assertIn("D5", rules_hit("This is really quite simply basically the best approach on 2 counts."))

    def test_code_blocks_are_untouched(self):
        text = "Run it.\n\n```python\nx = 'leverage robust seamless synergy'\n```\n"
        self.assertNotIn("H1", rules_hit(text))

    def test_frontmatter_is_skipped(self):
        text = "---\ntitle: leverage robust synergy\n---\n\nWe shipped 4 fixes on Tuesday.\n"
        self.assertNotIn("H1", rules_hit(text))

    def test_tables_are_skipped(self):
        text = "We shipped 4 fixes.\n\n| a | b |\n|---|---|\n| leverage | robust |\n"
        self.assertNotIn("H1", rules_hit(text))


class Suppression(unittest.TestCase):
    def test_whole_line_suppression(self):
        self.assertNotIn("H1", rules_hit("We leverage the gateway. <!-- clear: ignore -->"))

    def test_targeted_suppression(self):
        self.assertNotIn("H1", rules_hit("We leverage it. <!-- clear: ignore H1 -->"))

    def test_targeted_suppression_leaves_other_rules(self):
        hit = rules_hit("We leverage it prior to launch. <!-- clear: ignore H1 -->")
        self.assertIn("P5", hit)

    def test_voice_lint_compatibility(self):
        self.assertNotIn("H1", rules_hit("We leverage it. <!-- voice-lint: ignore -->"))


class Scoring(unittest.TestCase):
    def test_bad_fixture_fails_hard(self):
        r = score((FIXTURES / "bad.md").read_text())
        self.assertLess(r["score"], 60, r["score"])
        self.assertGreater(r["counts"]["error"], 5)
        self.assertEqual(r["band"], "F")

    def test_good_fixture_ships(self):
        r = score((FIXTURES / "good.md").read_text())
        self.assertGreater(r["score"], 90, r["score"])
        self.assertEqual(r["counts"]["error"], 0)

    def test_score_tracks_density_not_length(self):
        """Same slop per word, different lengths, comparable score."""
        unit = "We leverage the robust gateway and it is seamless for the whole team here. "
        mid = score(unit * 25)["axis_scores"]["human"]
        long = score(unit * 75)["axis_scores"]["human"]
        self.assertAlmostEqual(mid, long, delta=6, msg=f"{mid} vs {long}")

    def test_score_is_deterministic(self):
        text = (FIXTURES / "bad.md").read_text()
        self.assertEqual(score(text)["score"], score(text)["score"])

    def test_stats_are_reported(self):
        r = score((FIXTURES / "good.md").read_text())
        for key in ("words", "sentences", "grade_level", "reading_ease", "sentence_stdev"):
            self.assertIn(key, r["stats"])


class Cli(unittest.TestCase):
    def run_cli(self, *args) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "clearcheck.py"), *args],
            capture_output=True, text=True, cwd=ROOT)

    def test_good_fixture_exits_zero(self):
        p = self.run_cli("tests/fixtures/good.md", "--no-color")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_bad_fixture_exits_one(self):
        p = self.run_cli("tests/fixtures/bad.md", "--no-color")
        self.assertEqual(p.returncode, 1)

    def test_json_output_parses(self):
        p = self.run_cli("tests/fixtures/good.md", "--json")
        data = json.loads(p.stdout)
        self.assertIn("axis_scores", data)
        self.assertIn("findings", data)

    def test_explain_prints_the_rule(self):
        p = self.run_cli("--explain", "H6")
        self.assertEqual(p.returncode, 0)
        self.assertIn("negative parallelism", p.stdout.lower())

    def test_list_rules(self):
        p = self.run_cli("--list-rules")
        self.assertEqual(p.stdout.count("\n"), len(PACK["rules"]))

    def test_missing_file_is_a_usage_error(self):
        self.assertEqual(self.run_cli("no/such/file.md").returncode, 2)

    def test_unknown_profile_fails(self):
        self.assertNotEqual(self.run_cli("tests/fixtures/good.md", "--profile", "nope").returncode, 0)

    def test_gate_flag_is_honored(self):
        self.assertEqual(self.run_cli("tests/fixtures/good.md", "--gate", "99").returncode, 1)
        self.assertEqual(self.run_cli("tests/fixtures/good.md", "--gate", "50").returncode, 0)

    def test_stdin(self):
        p = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "clearcheck.py"), "--stdin", "--json"],
            input="We shipped 4 fixes on Tuesday. The loader validates the config first.",
            capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(json.loads(p.stdout)["counts"]["error"], 0)


class Targets(unittest.TestCase):
    def test_targets_are_current(self):
        p = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "compile_targets.py"), "--check"],
            capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(p.returncode, 0, p.stdout)

    def test_skill_frontmatter(self):
        text = (ROOT / "SKILL.md").read_text()
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("name: clearmode", text)
        self.assertIn("description:", text)

    def test_cursor_rule_stays_small(self):
        body = (ROOT / "targets" / "cursor" / "clearmode.mdc").read_text().split("---", 2)[2]
        self.assertLess(len(body.split()), 220, "always-apply rule costs tokens on every request")

    def test_grok_block_fits_a_text_box(self):
        self.assertLess(len((ROOT / "targets" / "grok" / "custom-instructions.txt").read_text()), 3100)

    def test_repo_prose_has_no_em_dashes(self):
        for name in ("README.md", "AGENTS.md", "CLEAR-100.md", "SKILL.md"):
            self.assertNotIn(cc.EM_DASH, (ROOT / name).read_text(), name)

    def test_repo_passes_its_own_standard(self):
        for name in ("README.md", "CLEAR-100.md"):
            r = score((ROOT / name).read_text(), "technical")
            self.assertEqual(r["counts"]["error"], 0, f"{name}: {r['findings'][:2]}")
            self.assertGreater(r["score"], 85, f"{name} scored {r['score']}")


if __name__ == "__main__":
    unittest.main()
