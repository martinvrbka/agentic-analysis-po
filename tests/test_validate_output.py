"""validate_output.py: format contracts, budgets, and the retry-capped Stop hook."""
import json
import os
import unittest

from helpers import readf, FIXTURES, ProjectTest

import validate_output as vo


def fixture_lines(name):
    return readf(os.path.join(FIXTURES, name), encoding="utf-8").splitlines()


class ContractTest(unittest.TestCase):
    def test_good_fixtures_pass(self):
        self.assertEqual(vo.check_analyst(fixture_lines("r1-analyst.md"), "small"), [])
        self.assertEqual(vo.check_designer(fixture_lines("r1-designer-response.md"), "small",
                                           "r1-designer-response.md"), [])
        self.assertEqual(vo.check_stories(fixture_lines("user-stories.md"), "small"), [])
        self.assertEqual(vo.check_coverage(fixture_lines("coverage-report.md"), "small"), [])

    def test_analyst_contract(self):
        lines = fixture_lines("r1-analyst.md")
        bad = [l.replace("NEW_ISSUES: 3", "NEW_ISSUES: 5").replace("| minor |", "| low |") for l in lines]
        errs = "\n".join(vo.check_analyst(bad, "small"))
        self.assertIn("NEW_ISSUES says 5", errs)
        self.assertIn("Severity must be", errs)
        extra = lines[:6] + ["| F1.9 | second-data-finding | Data | NEW | minor | second data finding | §1 |"] + lines[6:]
        extra = [l.replace("NEW_ISSUES: 3", "NEW_ISSUES: 4") for l in extra]
        self.assertIn("2 NEW findings in Data", "\n".join(vo.check_analyst(extra, "small")))
        self.assertEqual(vo.check_analyst(extra, "standard"), [])

    def test_designer_question_blocks(self):
        lines = fixture_lines("r1-designer-response.md")
        no_block = [l for l in lines if not l.startswith("### DL-001")]
        self.assertIn("without a '### DL-001' block",
                      "\n".join(vo.check_designer(no_block, "small", "r1-designer-response.md")))
        long_label = [l.replace("1. Admins only —", "1. Admins only and nobody else at all —") for l in lines]
        self.assertIn("longer than 5 words",
                      "\n".join(vo.check_designer(long_label, "small", "r1-designer-response.md")))
        self.assertIn("Follow-on edits", "\n".join(vo.check_designer(["| DL id | PRD section |"], "small",
                                                                     "r1-designer-apply.md")))

    def test_prd_needs_terms_and_stories_need_slices(self):
        self.assertEqual(vo.check_prd(fixture_lines("prd-draft.md"), "small"), [])
        no_terms = [l for l in fixture_lines("prd-draft.md") if not l.startswith("### Terms")]
        self.assertIn("### Terms", "\n".join(vo.check_prd(no_terms, "small")))
        no_slice = [l for l in fixture_lines("user-stories.md") if not l.startswith("Slice:")]
        self.assertIn("US-01 has no 'Slice:' line", "\n".join(vo.check_stories(no_slice, "small")))

    def test_final_package_sections(self):
        lines = [f"## {n}. Section" for n in range(9)]
        errs = "\n".join(vo.check_final(lines, "small"))
        self.assertIn("'## 9.'", errs)
        self.assertIn("'## 11.'", errs)
        self.assertEqual(vo.check_final([f"## {n}. Section" for n in range(12)], "small"), [])

    def test_story_budgets(self):
        lines = fixture_lines("user-stories.md") + [""] * 100
        self.assertIn("over the small budget of 90", "\n".join(vo.check_stories(lines, "small")))
        two = fixture_lines("user-stories.md")[:26]
        self.assertIn("2 stories; the small range is 3–6", "\n".join(vo.check_stories(two, "small")))


class RetroTest(unittest.TestCase):
    CARD = ["## Scorecard", "| Metric | Score | Why (evidence) |", "|---|---|---|",
            "| Understandability | 4 | x |", "| Clarity | 3 | x |", "| Completeness | 5 | x |",
            "| Testability | 4 | x |", "| Proportion | 2 | x |", "| Product focus | 5 | x |", "Trend: First scored run.",
            "## A. Package", "## B. Recommendations for the analysis app"]

    def test_complete_scorecard_passes(self):
        self.assertEqual(vo.check_retro(["# Retro"] + self.CARD, "small"), [])

    def test_missing_or_bad_scores_fail(self):
        bad = [l.replace("| Clarity | 3 |", "| Clarity | good |") for l in self.CARD if not l.startswith("Trend")]
        errs = "\n".join(vo.check_retro(bad, "small"))
        self.assertIn("'| Clarity | <1–5>", errs)
        self.assertIn("'Trend:' line", errs)


class HookTest(ProjectTest):
    def test_stop_hook_blocks_once_then_records(self):
        run = self.start()
        bad = [l.replace("NEW_ISSUES: 3", "NEW_ISSUES: 9") for l in fixture_lines("r1-analyst.md")]
        self.write(f"{run['run']}/rounds/r1-analyst.md", "\n".join(bad))
        payload = json.dumps({"agent_id": "a1", "hook_event_name": "SubagentStop"})
        first = self.run_script("validate_output.py", "--hook", "analyst", stdin=payload)
        self.assertEqual(first.returncode, 2)
        self.assertIn("NEW_ISSUES says 9", first.stderr)
        second = self.run_script("validate_output.py", "--hook", "analyst", stdin=payload)
        self.assertEqual(second.returncode, 0, "the retry cap lets the agent stop")
        warnings = readf(self.path(run["feature"], ".state", "validation-warnings.log"), encoding="utf-8")
        self.assertIn("analyst", warnings)

    def test_stop_hook_passes_good_output(self):
        run = self.start()
        self.fixture("r1-analyst.md", f"{run['run']}/rounds/r1-analyst.md")
        r = self.run_script("validate_output.py", "--hook", "analyst", stdin=json.dumps({"agent_id": "a2"}))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_consistency_between_files(self):
        run = self.start()
        W = run["run"]
        self.fixture("prd-draft.md", f"{W}/prd-draft.md")
        self.write(f"{W}/user-stories.md", readf(os.path.join(FIXTURES, "user-stories.md"))
                   + "\n## US-04: Scheduled exports sent by email\nAs an admin, I want exports mailed.\n")
        self.write(f"{W}/story-map.md", "| Export |\n|---|\n| US-01 |\n| US-09 |\n")
        problems = "\n".join(vo.consistency(self.path(W), "small"))
        self.assertIn("US-02 is a story but not in the map", problems)
        self.assertIn("US-09 is in the map but has no story", problems)
        self.assertIn("Covers DL-003 is not in the decision log", problems)
        self.assertIn("US-04 'Scheduled exports sent by email' looks like a Later", problems)
        self.assertNotIn("US-01 'Export orders' looks like", problems)

    def test_package_lint_flags_altitude_and_unlogged_questions(self):
        run = self.start()
        self.write(f"{run['run']}/user-stories.md",
                   readf(os.path.join(FIXTURES, "user-stories.md"), encoding="utf-8")
                   + "\nThen the API returns HTTP 500\n")
        r = self.run_script("validate_output.py", "package", run["run"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("technical word 'API'", r.stdout)
        self.assertIn("user-stories.md:27: 🔵 open question not in the decision log", r.stdout)

    def test_after_checks_first_coverage_report_as_coverage(self):
        self.assertEqual(vo.kind_of_file("coverage-report-1.md"), "coverage")
        self.assertEqual(vo.kind_of_file("coverage-report.md"), "coverage")
        self.assertEqual(vo.kind_of_file("rounds/r2-analyst.md"), "analyst")
        self.assertEqual(vo.kind_of_file("rounds/rP-designer-apply.md"), "designer")
        run = self.start()
        self.fixture("coverage-report.md", f"{run['run']}/coverage-report-1.md")
        r = self.run_script("validate_output.py", "--after", "coverage-checker", "coverage-report-1.md")
        self.assertEqual(r.stdout.strip(), "OK", "a coverage report must not get the designer's checks")

    def test_package_lint_flags_unlogged_question_in_final_prd(self):
        run = self.start()
        self.write(f"{run['run']}/final-prd.md", "## 3. Terms\n- profile: 🔵 Open Question: what does it hold?\n")
        r = self.run_script("validate_output.py", "package", run["run"])
        self.assertIn("final-prd.md:2: 🔵 open question not in the decision log", r.stdout)


if __name__ == "__main__":
    unittest.main()
