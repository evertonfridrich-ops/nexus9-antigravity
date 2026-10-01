from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nexus9.guard import GuardError
from nexus9.policy import RuntimePolicy
from nexus9.suite import Suite


class RuntimePolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "project"
        self.root.mkdir()
        self.suite = Suite(self.root, self.base / "state", RuntimePolicy("light", "external", "external"))

    def write(self, path, text):
        target = self.root / path
        target.write_text(text, encoding="utf-8")
        return target

    def test_ownership_blocks_valid_operations_and_embedded_memory_references(self):
        for operation, values, manage in [("memory_save", {"body": {"goal": "no write"}}, True),
                ("memory", {}, False), ("resume", {}, False),
                ("compress", {"blocks": [{"id": "a", "text": "text"}]}, False),
                ("context", {"task": "inspect", "memory": "default"}, False)]:
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(GuardError, "disabled"):
                    (self.suite.manage if manage else self.suite.query)(operation, values)
        with self.suite.guard.connect() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM memories").fetchone()[0], 0)

    def test_catalog_has_three_tool_protocol_with_disabled_operations_disclosed(self):
        catalog = self.suite.catalog()
        self.assertEqual(len(catalog["heads"]), 9)
        self.assertIn("memory_save", catalog["runtime_policy"]["disabled_operations"])
        with self.assertRaises(GuardError):
            self.suite.catalog("memory_save")
        self.assertNotIn("logs", self.suite.query("plan", {"task": "debug error"})["operations"])

    def test_light_refresh_limits_new_parses_and_rotates_to_later_files(self):
        for i in range(40):
            self.write(f"file{i:02}.py", f"def f{i}():\n    return {i}\n")
        first = self.suite.query("index", {"max_files": 1000})
        self.assertEqual(first["reparsed"], 24)
        self.assertTrue(first["limited"])
        second = self.suite.query("index", {"max_files": 1000})
        self.assertEqual(second["indexed"], 40)
        self.assertLessEqual(second["reparsed"], 24)

    def test_cached_discovery_still_reads_changed_source_and_new_dependency(self):
        self.write("main.py", "def calculate():\n    return 1\n")
        self.suite.query("context", {"task": "calculate", "paths": ["main.py"]})
        self.write("dep.py", "def answer():\n    return 99\n")
        self.write("main.py", "from dep import answer\ndef calculate():\n    return answer()\n")
        with patch.object(self.suite.index, "refresh", side_effect=AssertionError("global rescan must be cached")):
            result = self.suite.query("context", {"task": "calculate", "paths": ["main.py"],
                                                  "focus_symbols": {"main.py": "calculate"}})
        self.assertTrue(result["coverage"]["index_cached"])
        self.assertTrue(any(i["path"] == "dep.py" and "return 99" in i["text"] for i in result["items"]))
        self.assertTrue(any("return answer()" in i["text"] for i in result["items"]))

    def test_oversized_light_source_is_visible_as_limited_and_rejected_explicitly(self):
        self.write("big.py", "# noise\n" * 70000)
        report = self.suite.query("index")
        self.assertTrue(report["limited"])
        self.assertEqual(report["skipped"], 1)
        with self.assertRaisesRegex(GuardError, "hardware profile"):
            self.suite.query("outline", {"path": "big.py"})
        with self.assertRaisesRegex(GuardError, "hardware profile"):
            self.suite.query("verify", {"path": "big.py"})

    def test_health_reports_integrity_without_background_workers_or_embeddings(self):
        health = self.suite.query("health")
        self.assertEqual(health["state_integrity"], "ok")
        self.assertEqual(health["runtime_policy"]["hardware"], "light")
        self.assertEqual(health["runtime_policy"]["background_workers"], 0)
        self.assertFalse(health["runtime_policy"]["embeddings"])

    def test_light_inventory_is_bounded_but_explicit_sources_remain_available(self):
        for i in range(520):
            self.write(f"file{i:03}.py", f"def f{i}():\n    return {i}\n")
        standard = Suite(self.root, self.base / "state", RuntimePolicy("standard"))
        self.assertEqual(standard.query("index", {"max_files": 1000})["indexed"], 520)
        self.assertEqual(len(self.suite.index.files()), 512)
        self.assertTrue(self.suite.index.files_limited)
        result = self.suite.query("context", {"task": "inspect f0", "paths": ["file000.py"],
                                              "focus_symbols": {"file000.py": "f0"}})
        self.assertTrue(any("return 0" in item["text"] for item in result["items"]))
        self.assertTrue(result["coverage"]["index_limited"])
