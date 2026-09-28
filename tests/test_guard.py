"""The guard must pin every agent to the active feature and run, and keep the analyst away from designer rounds."""
import json
import unittest

from helpers import ProjectTest

import guard

W = "groomed/order-export/run-2_2026-01-02"
P = "groomed/order-export/run-1_2026-01-01"


class GuardTest(ProjectTest):
    def setUp(self):
        super().setUp()
        self.write("groomed/.active-run.json", json.dumps(
            {"slug": "order-export", "feature": "groomed/order-export", "run": W, "prev": P, "k": 2, "tier": "small"}))

    def allowed(self, role, path, tool="Read"):
        return guard.decide(role, tool, path, self.root) is None

    def test_agents_can_read_their_inputs_in_the_active_run(self):
        for role, path in [("analyst", f"{W}/prd-draft.md"), ("analyst", "groomed/order-export/decision-log.md"),
                           ("designer", f"{W}/rounds/r1-analyst.md"), ("prd-drafter", f"{P}/prd-draft.md"),
                           ("story-writer", f"{P}/user-stories.md"), ("retro", f"{W}/rounds/r1-designer-response.md"),
                           ("prd-drafter", "personas/prd-development/examples/sample.md"), ("analyst", "CLAUDE.md")]:
            self.assertTrue(self.allowed(role, path), f"{role} should read {path}")

    def test_product_context_is_readable_by_all_and_writable_by_none(self):
        for role in guard.ROLES:
            self.assertTrue(self.allowed(role, "context/product-context.md"), role)
            self.assertFalse(self.allowed(role, "context/product-context.md", "Write"), role)
        self.assertTrue(self.allowed("packager", f"{W}/readiness.md"))
        self.assertFalse(self.allowed("packager", f"{W}/readiness.md", "Write"), "readiness is written by script")

    def test_analyst_never_sees_designer_rounds(self):
        self.assertFalse(self.allowed("analyst", f"{W}/rounds/r1-designer-response.md"))

    def test_other_features_archives_and_older_runs_are_out_of_reach(self):
        for role, path in [("analyst", "groomed/other-feature/confirmed-facts.md"),
                           ("designer", "groomed/other-feature/confirmed-facts.md"),
                           ("analyst", "groomed/_archive/order-export_2025/run-1_2025-01-01/prd-draft.md"),
                           ("analyst", f"{P}/prd-draft.md"),
                           ("designer", f"{P}/rounds/r1-analyst.md")]:
            self.assertFalse(self.allowed(role, path), f"{role} must not read {path}")

    def test_star_does_not_cross_folders(self):
        self.assertFalse(self.allowed("designer", f"{W}/rounds/old/r1-analyst.md"))
        self.assertFalse(self.allowed("prd-drafter", "personas/prd-development/a/b/c.md"))

    def test_writes_only_to_own_files(self):
        self.assertTrue(self.allowed("analyst", f"{W}/rounds/r2-analyst.md", "Write"))
        self.assertFalse(self.allowed("analyst", f"{W}/prd-draft.md", "Write"))
        self.assertFalse(self.allowed("designer", "groomed/order-export/decision-log.md", "Edit"))
        self.assertFalse(self.allowed("packager", f"{P}/final-prd.md", "Write"))

    def test_other_tools_and_outside_paths_are_blocked(self):
        self.assertIn("may only use", guard.decide("analyst", "Bash", "x", self.root))
        self.assertIn("outside the project", guard.decide("analyst", "Read", "/etc/passwd", self.root))
        self.assertIn("unknown role", guard.decide("nobody", "Read", "CLAUDE.md", self.root))

    def test_without_an_active_run_only_shared_files_are_readable(self):
        import os
        os.remove(self.path("groomed", ".active-run.json"))
        self.assertTrue(self.allowed("analyst", "CLAUDE.md"))
        self.assertFalse(self.allowed("analyst", f"{W}/prd-draft.md"))
        self.assertFalse(self.allowed("analyst", f"{W}/rounds/r1-analyst.md", "Write"))

    def test_hook_exit_codes(self):
        payload = lambda path: json.dumps({"tool_name": "Read", "tool_input": {"file_path": path}, "cwd": self.root})
        self.assertEqual(self.run_script("guard.py", "analyst", stdin=payload(f"{W}/prd-draft.md")).returncode, 0)
        r = self.run_script("guard.py", "analyst", stdin=payload("groomed/other/confirmed-facts.md"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("[guard]", r.stderr)



class AutoRoleTest(ProjectTest):
    """`guard.py --auto` is for a project-level hook: the role comes from the payload's agent_type."""

    def guard(self, payload):
        return self.run_script("guard.py", "--auto", stdin=json.dumps(payload))

    def test_pipeline_agent_is_guarded_and_main_session_is_not(self):
        read = {"tool_name": "Read", "tool_input": {"file_path": "README.md"}, "cwd": self.root}
        self.assertEqual(self.guard(dict(read, agent_type="analyst")).returncode, 2)
        self.assertEqual(self.guard(read).returncode, 0, "the main session has no agent_type")
        self.assertEqual(self.guard(dict(read, agent_type="Explore")).returncode, 0, "other agents are not pipeline roles")


if __name__ == "__main__":
    unittest.main()
