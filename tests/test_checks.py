"""Safe generated unittest projects exercise the opt-in runner, never real apps."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nexus9.check_models import CheckRun
from nexus9.checks import CheckRunner, MAX_RUNS, OUTPUT_BYTES
from nexus9.guard import Engine, GuardError


class CheckRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "project"
        self.root.mkdir()
        self.guard = Engine(self.root, self.base / "state")
        self.runner = CheckRunner(self.guard, enabled=True)
        self.write("tests/__init__.py", "")
        self.write("source.py", "VALUE = 1\n")
        self.profile()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def profile(self, **changes):
        definition = {"kind": "python_unittest", "start_dir": "tests", "pattern": "test_*.py", "timeout_seconds": 4}
        definition.update(changes)
        self.write("nexus9-checks.json", json.dumps({"profiles": {"unit": definition}}))

    def write_test(self, body="self.assertEqual(1 + 1, 2)"):
        self.write("tests/test_generated.py", "import unittest\nclass Generated(unittest.TestCase):\n    def test_generated(self):\n        " + body + "\n")

    def test_disabled_refuses_before_config_or_process_access(self):
        disabled = CheckRunner(self.guard)
        with patch.object(disabled, "_configuration", side_effect=AssertionError("must not read")):
            with self.assertRaisesRegex(GuardError, "disabled"):
                disabled.run("unit", ["source.py"])
            self.assertFalse(disabled.profiles()["enabled"])

    def test_actual_passing_process_has_immutable_source_fingerprints(self):
        self.write_test()
        result = self.runner.run("unit", ["source.py"])
        self.assertTrue(result["passed"], result)
        self.assertTrue(result["fresh"])
        self.assertEqual(result["tests_run"], 1)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["provenance"], "nexus9_observed_process")
        self.assertEqual(set(result["source_hashes"]), {"nexus9-checks.json", "source.py", "tests/__init__.py", "tests/test_generated.py"})
        self.assertEqual(CheckRunner(self.guard).get_run(result["run_id"])["receipt_sha256"], result["receipt_sha256"])

    def test_failing_tests_are_observed_as_failure(self):
        self.write_test("self.assertEqual(1, 2)")
        result = self.runner.run("unit")
        self.assertFalse(result["passed"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["tests_run"], 1)
        self.assertEqual(result["exit_code"], 1)

    def test_workspace_cannot_shadow_fixed_unittest_runner_module(self):
        self.write_test()
        self.write("unittest.py", "raise RuntimeError('shadow module must not run')\n")
        self.write("sitecustomize.py", "print('shadow sitecustomize must not run')\n")
        result = self.runner.run("unit")
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["tests_run"], 1)
        self.assertNotIn("must not run", result["output"])

    def test_zero_tests_does_not_pass(self):
        result = self.runner.run("unit")
        self.assertFalse(result["passed"])
        self.assertEqual(result["status"], "no_tests")
        self.assertEqual(result["tests_run"], 0)

    def test_all_skipped_tests_do_not_count_as_observed_pass(self):
        self.write("tests/test_generated.py", "import unittest\nclass Generated(unittest.TestCase):\n    @unittest.skip('unavailable')\n    def test_case(self): self.fail('must not run')\n")
        result = self.runner.run("unit")
        self.assertEqual(result["exit_code"], 0)
        self.assertFalse(result["passed"])
        self.assertEqual(result["tests_run"], 1)
        self.assertEqual(result["tests_skipped"], 1)
        self.assertEqual(result["tests_executed"], 0)
        self.assertEqual(result["status"], "no_executed_tests")

    def test_only_expected_failures_do_not_count_as_observed_pass(self):
        self.write("tests/test_generated.py", "import unittest\nclass Generated(unittest.TestCase):\n    @unittest.expectedFailure\n    def test_case(self): self.fail('known defect')\n")
        result = self.runner.run("unit")
        self.assertEqual(result["exit_code"], 0)
        self.assertFalse(result["passed"])
        self.assertEqual(result["tests_expected_failures"], 1)
        self.assertEqual(result["tests_passed"], 0)

    def test_timeout_does_not_pass(self):
        self.profile(timeout_seconds=1)
        self.write_test("__import__('time').sleep(10)")
        result = self.runner.run("unit")
        self.assertTrue(result["timed_out"])
        self.assertFalse(result["passed"])
        self.assertEqual(result["status"], "timeout")

    def test_source_change_or_deletion_invalidates_without_changing_receipt(self):
        self.write_test()
        result = self.runner.run("unit", ["source.py"])
        self.write("source.py", "VALUE = 2\n")
        changed = self.runner.get_run(result["run_id"])
        self.assertFalse(changed["fresh"])
        self.assertFalse(changed["passed"])
        self.assertTrue(changed["recorded_passed"])
        self.assertEqual(changed["receipt_sha256"], result["receipt_sha256"])
        self.assertIn("source.py", changed["changed_sources"])
        (self.root / "source.py").unlink()
        self.assertFalse(self.runner.get_run(result["run_id"])["fresh"])

    def test_new_unrelated_file_does_not_invalidate_explicit_scope(self):
        self.write_test()
        result = self.runner.run("unit", ["source.py"])
        self.write("unrelated.py", "VALUE = 3\n")
        self.assertTrue(self.runner.get_run(result["run_id"])["fresh"])

    def test_added_test_invalidates_receipt_of_previous_suite(self):
        self.write_test()
        result = self.runner.run("unit")
        self.write("tests/test_new.py", "import unittest\nclass New(unittest.TestCase):\n    def test_failure(self): self.fail('new case')\n")
        current = self.runner.get_run(result["run_id"])
        self.assertFalse(current["fresh"])
        self.assertFalse(current["passed"])
        self.assertIn("tests/test_new.py", current["changed_sources"])

    def test_ancestor_package_initializer_is_part_of_snapshot(self):
        self.write_test()
        self.write("__init__.py", "VALUE = 1\n")
        result = self.runner.run("unit")
        self.assertIn("__init__.py", result["source_hashes"])
        self.write("__init__.py", "VALUE = 2\n")
        self.assertFalse(self.runner.get_run(result["run_id"])["fresh"])

    def test_source_mutated_during_test_cannot_pass(self):
        self.write_test("__import__('pathlib').Path('source.py').write_text('VALUE = 3')")
        result = self.runner.run("unit", ["source.py"])
        self.assertEqual(result["status"], "needs_revalidation")
        self.assertEqual(result["recorded_status"], "source_changed")
        self.assertFalse(result["passed"])
        self.assertIn("source.py", result["source_changed_during_run"])

    def test_output_is_bounded_and_redacted(self):
        self.write_test("print('n' * 40000, flush=True); print('password=synthetic-sensitive-value', flush=True)")
        result = self.runner.run("unit")
        self.assertTrue(result["passed"], result)
        self.assertTrue(result["output_truncated"])
        self.assertLessEqual(len(result["output"].encode()), OUTPUT_BYTES)
        self.assertNotIn("synthetic-sensitive-value", result["output"])
        self.assertIn("[REDACTED]", result["output"])

    def test_profile_listing_has_no_raw_commands(self):
        listing = self.runner.profiles()
        self.assertEqual(listing["profiles"], [{"name": "unit", "kind": "python_unittest"}])
        self.assertNotIn("start_dir", json.dumps(listing))
        self.assertNotIn("command", json.dumps(listing))

    def test_unknown_invalid_or_oversized_profiles_are_rejected_without_execution(self):
        with self.assertRaisesRegex(GuardError, "unknown"):
            self.runner.run("missing")
        for definition in ["{\"profiles\":{},\"profiles\":{}}", "x" * 17000,
                           json.dumps({"profiles": {"unit": {"kind": "shell", "start_dir": "tests"}}})]:
            self.write("nexus9-checks.json", definition)
            with self.assertRaises(GuardError):
                self.runner.run("unit")

    def test_traversal_secrets_and_profile_command_fields_are_rejected(self):
        self.write_test()
        for path in ("../outside.py", ".env", "C:/secret.py"):
            with self.subTest(path=path), self.assertRaises(GuardError):
                self.runner.run("unit", [path])
        self.profile(start_dir="../outside")
        with self.assertRaises(GuardError):
            self.runner.run("unit")
        self.profile(command="echo unsafe")
        with self.assertRaises(GuardError):
            self.runner.run("unit")

    def test_receipt_capacity_refuses_before_process_execution(self):
        self.write_test()
        with self.guard.connect() as con:
            for index in range(MAX_RUNS):
                con.execute("INSERT INTO check_runs VALUES(?,?)", (f"old-{index}", "{}"))
        with patch.object(self.runner, "_execute", side_effect=AssertionError("must not execute")):
            with self.assertRaisesRegex(GuardError, "capacity"):
                self.runner.run("unit")

    def test_missing_run_is_not_a_passing_receipt(self):
        with self.assertRaisesRegex(GuardError, "not found"):
            self.runner.get_run("missing")

    def test_schema_rejects_arbitrary_process_parameters(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            CheckRun.model_validate({"profile": "unit", "sources": [], "command": "unsafe"})


if __name__ == "__main__":
    unittest.main()
