"""End-to-end evidence workflow using isolated, trusted synthetic projects."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from nexus9.guard import GuardError
from nexus9.policy import RuntimePolicy
from nexus9.runtime import RuntimeIdentity
from nexus9.suite import Suite


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "project"
        self.root.mkdir()
        self.suite = Suite(self.root, self.base / "state")
        (self.root / "main.py").write_text("def answer():\n    return 1\n", encoding="utf-8")

    def body(self, run_id=None):
        return {"objective": "Demonstrate the answer behavior", "hypotheses": [{"id": "h", "statement": "answer returns 1"}],
                "evidence": [{"id": "e", "summary": "Observed source and test", "hypothesis_ids": ["h"],
                              "result": "supports", "files": ["main.py"], "run_id": run_id}],
                "conclusions": [{"id": "c", "statement": "Answer behavior is supported", "evidence_ids": ["e"], "hypothesis_ids": ["h"]}],
                "criteria": [{"id": "accept", "requirement": "Reproduce the behavior", "conclusion_ids": ["c"], "requires_observed_test": True}]}

    def setup_tests(self):
        (self.root / "tests").mkdir()
        (self.root / "tests/__init__.py").write_text("", encoding="utf-8")
        (self.root / "tests/test_answer.py").write_text(
            "import unittest\nfrom main import answer\nclass TestAnswer(unittest.TestCase):\n"
            "    def test_answer(self):\n        self.assertEqual(answer(), 1)\n", encoding="utf-8")
        (self.root / "nexus9-checks.json").write_text(json.dumps({"profiles": {"regression": {
            "kind": "python_unittest", "start_dir": "tests", "pattern": "test_*.py", "timeout_seconds": 5}}}), encoding="utf-8")

    def test_default_does_not_execute_tests_or_trust_reported_evidence(self):
        self.suite.manage("investigation_save", {"name": "case", "body": self.body()})
        report = self.suite.query("investigation", {"name": "case"})
        self.assertNotEqual(report["status"], "supported_by_current_evidence")
        self.assertFalse(self.suite.query("check_profiles")["enabled"])
        with self.assertRaises(GuardError):
            self.suite.manage("check_run", {"profile": "regression"})

    def test_observed_run_source_change_and_explicit_revalidation(self):
        self.setup_tests()
        self.suite = Suite(self.root, self.base / "state", enable_test_runner=True)
        run = self.suite.manage("check_run", {"profile": "regression", "sources": ["main.py"]})
        self.assertTrue(run["passed"], run)
        self.assertGreater(run["source_count"], 1)
        self.assertNotIn("source_hashes", run)
        self.suite.manage("investigation_save", {"name": "case", "body": self.body(run["run_id"])})
        report = self.suite.query("investigation", {"name": "case"})
        self.assertEqual(report["status"], "supported_by_current_evidence", report)
        # A source can change without changing behavior: proof still needs rerun.
        (self.root / "main.py").write_text("def answer():\n    return 1  # edited\n", encoding="utf-8")
        stale = self.suite.query("investigation", {"name": "case"})
        self.assertTrue(stale["revalidation_required"])
        self.assertNotEqual(stale["status"], "supported_by_current_evidence")
        fresh_run = self.suite.manage("check_run", {"profile": "regression", "sources": ["main.py"]})
        self.assertTrue(fresh_run["passed"])
        updated = self.body(fresh_run["run_id"])
        updated["evidence"][0]["id"] = "e2"
        updated["conclusions"][0]["evidence_ids"] = ["e2"]
        self.suite.manage("investigation_save", {"name": "case", "expected_revision": 1, "body": updated})
        current = self.suite.query("investigation", {"name": "case"})
        self.assertEqual(current["status"], "supported_by_current_evidence", current)
        restarted = Suite(self.root, self.base / "state", enable_test_runner=True)
        self.assertEqual(restarted.query("investigation", {"name": "case"})["revision"], 2)

    def test_planning_context_and_handoff_include_current_investigation_brief(self):
        body = self.body()
        self.suite.manage("investigation_save", {"name": "case", "body": body})
        for op in ("plan", "route", "context", "handoff"):
            values = {"task": "Inspect answer", "investigation": "case"}
            if op in {"context", "handoff"}:
                values["paths"] = ["main.py"]
            report = self.suite.query(op, values)
            self.assertEqual(report["investigation"]["name"], "case")
        status = self.suite.query("runtime_status")
        self.assertEqual(status["version"], "0.4.0")
        self.assertEqual(status["last_context_delivery"]["operation"], "handoff")
        self.assertFalse(status["host_skill_loaded_verified"])
        self.assertFalse(status["automatic_update"])

    def test_external_owner_blocks_graph_and_runner_operations(self):
        suite = Suite(self.root, self.base / "state", RuntimePolicy(memory_owner="external"))
        for op, values, write in [("investigation", {"name": "x"}, False),
                                  ("regression_cases", {}, False), ("check_profiles", {}, False),
                                  ("check_result", {"run_id": "x"}, False),
                                  ("investigation_save", {"name": "x", "body": self.body()}, True),
                                  ("check_run", {"profile": "regression"}, True),
                                  ("plan", {"task": "Inspect", "investigation": "x"}, False)]:
            with self.subTest(op=op), self.assertRaisesRegex(GuardError, "disabled"):
                (suite.manage if write else suite.query)(op, values)

    def test_metadata_recipes_are_extensible_without_loading_plugin_code(self):
        known = self.suite.query("domain_pack")
        self.assertEqual({x["id"] for x in known["packs"]}, {"generic", "crypto-institutional"})
        recipe = {"schema_version": "1.0", "packs": [{"id": "mobile", "title": "Mobile app",
            "scope": "Foreground location", "invariants": ["Respect runtime permissions"],
            "evidence": ["Device test"], "external_tools": []}]}
        (self.root / "nexus9-domains.json").write_text(json.dumps(recipe), encoding="utf-8")
        domain = self.suite.query("domain_pack", {"name": "mobile"})
        self.assertFalse(domain["executes_plugin_code"])
        self.assertFalse(domain["external_tools_verified"])
        recipe["packs"][0]["id"] = "generic"
        (self.root / "nexus9-domains.json").write_text(json.dumps(recipe), encoding="utf-8")
        with self.assertRaises(GuardError):
            self.suite.query("domain_pack")

    def test_append_preserves_omitted_non_generic_domain(self):
        body = self.body()
        body["domain"] = "crypto-institutional"
        self.suite.manage("investigation_save", {"name": "crypto", "body": body})
        self.suite.manage("investigation_save", {"name": "crypto", "expected_revision": 1,
            "body": {"objective": body["objective"], "notes": [{"id": "note", "text": "Observed after restart"}]}})
        report = self.suite.query("investigation", {"name": "crypto"})
        self.assertEqual(report["domain"], "crypto-institutional")
        self.assertEqual(report["revision"], 2)

    def test_runtime_status_detects_disk_drift_without_claiming_loaded_code(self):
        package = self.base / "runtime"
        package.mkdir()
        (package / "module.py").write_text("value = 1\n", encoding="utf-8")
        identity = RuntimeIdentity(package)
        initial = identity.status()
        self.assertFalse(initial["restart_required"])
        (package / "module.py").write_text("value = 2\n", encoding="utf-8")
        changed = identity.status()
        self.assertTrue(changed["restart_required"])
        self.assertEqual(initial["files_at_startup_sha256"], changed["files_at_startup_sha256"])
        self.assertNotEqual(initial["current_files_sha256"], changed["current_files_sha256"])


if __name__ == "__main__":
    unittest.main()
