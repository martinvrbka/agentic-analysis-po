"""Consistency of the pipeline definition: budgets, agent wiring, persona snapshots."""
import glob
import hashlib
import os
import re
import unittest

from helpers import readf, REPO

import guard
from pipeline_common import budgets


def read(*parts):
    return readf(os.path.join(REPO, *parts), encoding="utf-8")


def frontmatter(path):
    return readf(path, encoding="utf-8").split("---")[1]


class BudgetsTest(unittest.TestCase):
    """CLAUDE.md states the budgets for humans and agents; budgets.json is what the scripts enforce."""

    def test_claude_md_matches_budgets_json(self):
        md = read("CLAUDE.md")
        rows = {m.group(1).strip(): m.group(0) for m in re.finditer(r"^\|([^|]+)\|.*$", md, re.M)}
        b = budgets()["tiers"]
        small, std = b["small"], b["standard"]
        self.assertIn(f"≤ {small['lines']['prd-draft.md']} lines", rows["`prd-draft.md`"])
        self.assertIn(f"≤ {std['lines']['prd-draft.md']} lines", rows["`prd-draft.md`"])
        self.assertIn(f"≤ {small['lines']['final-prd.md']} lines", rows["`final-prd.md`"])
        self.assertIn(f"≤ {std['lines']['final-prd.md']} lines", rows["`final-prd.md`"])
        stories = rows["Stories"]
        for t in (small, std):
            self.assertIn(f"{t['stories'][0]}–{t['stories'][1]}", stories)
            self.assertIn(f"{t['scenarios'][0]}–{t['scenarios'][1]} scenarios", stories)
            self.assertIn(f"≤ {t['lines']['user-stories.md']}", stories)
        maps = rows["`story-map.md` / `business-case.md`"]
        self.assertIsNone(small["lines"]["story-map.md"], "small features have no story map")
        self.assertIn(f"none (a `Slice:` line per story) / ≤ {small['lines']['business-case.md']} lines", maps)
        self.assertIn(f"≤ {std['lines']['story-map.md']} / ≤ {std['lines']['business-case.md']} lines", maps)
        dod = rows["Definition of Done"]
        for t in (small, std):
            self.assertIn(f"{t['dod'][0]}–{t['dod'][1]} items", dod)
        self.assertIn(f"max {small['rounds']}", rows["Debate rounds"])
        self.assertIn(f"max {std['rounds']}", rows["Debate rounds"])
        analyst = rows["Analyst NEW findings per round"]
        for t in (small, std):
            self.assertIn(f"≤ {t['new_per_dimension']} per dimension, ≤ {t['compounding']} compounding", analyst)
        self.assertIn(f"{budgets()['small_max_words']} words", md)
        self.assertIn(f"{budgets()['max_po_questions']} questions per run", md)
        self.assertIn(f"Stage 1 asks at most {budgets()['max_stage1_questions']}", md)
        self.assertIn(f"**at most {budgets()['max_stage1_questions']}** questions", read(".claude", "commands", "groom.md"))
        self.assertIn(f"≤ {budgets()['tiers']['small']['lines']['retro.md']} lines", read(".claude", "agents", "retro.md"))


class AgentWiringTest(unittest.TestCase):
    AGENTS = sorted(glob.glob(os.path.join(REPO, ".claude", "agents", "*.md")))

    def test_every_agent_is_guarded_validated_and_limited(self):
        self.assertTrue(self.AGENTS)
        for path in self.AGENTS:
            fm = frontmatter(path)
            role = re.search(r"^name:\s*(\S+)", fm, re.M).group(1)
            with self.subTest(role=role):
                self.assertIn(role, guard.ROLES, "every agent needs a guard role")
                self.assertIn(f'guard.py" {role}', fm, "PreToolUse guard must use the agent's own role")
                self.assertIn(f'validate_output.py" --hook {role}', fm, "Stop hook must validate the agent's output")
                self.assertRegex(fm, r"maxTurns:\s*\d+")
                self.assertRegex(fm, r"model:\s*\S+")
                tools = {t.strip() for t in re.search(r"^tools:\s*(.+)$", fm, re.M).group(1).split(",")}
                self.assertTrue(tools <= {"Read", "Write", "Edit"}, tools)
                self.assertIn(f"`{role}`", read(".claude", "commands", "groom.md"),
                              "the orchestrator must spawn this agent somewhere")

    def test_guard_roles_have_agents(self):
        names = {re.search(r"^name:\s*(\S+)", frontmatter(p), re.M).group(1) for p in self.AGENTS}
        self.assertEqual(set(guard.ROLES), names)


class ReadabilityTest(unittest.TestCase):
    def test_readability_numbers(self):
        import run_metrics
        out = "\n".join(run_metrics.readability(["# Title", "We build a filter. It hides long recipes quickly.",
                                                   "| table | row |", "🔵 Open Question: which steps?"]))
        self.assertIn("reading time ≈ 1 min", out)
        self.assertIn("Prose sentences: 3", out)
        self.assertIn("🔵 1", out)
        self.assertIn("final-prd.md missing", run_metrics.readability(None)[0])


class PersonaTest(unittest.TestCase):
    def test_persona_snapshots_match_checksums(self):
        for line in read("personas", "SOURCES.sha256").splitlines():
            if not line.strip():
                continue
            digest, name = line.split(None, 1)
            name = name.strip().lstrip("*")
            with open(os.path.join(REPO, "personas", name), "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), digest, f"personas/{name} was edited")


if __name__ == "__main__":
    unittest.main()
