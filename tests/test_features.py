from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile
import unittest

from nexus9.guard import GuardError, encode
from nexus9.index import outline
from nexus9.suite import Suite, HEADS


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "project"
        self.root.mkdir()
        self.suite = Suite(self.root, self.base / "state")

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def fixture(self):
        self.write("src/location.ts", "export function getPosition(): number {\n  return 42;\n}\n")
        self.write("src/gps.ts", "import { getPosition } from './location';\nexport const startGPS = async () => {\n  const label = `brace } inside string`;\n  return getPosition();\n};\nexport function stopGPS() { return false; }\n")
        self.write("src/screen.tsx", "import { startGPS } from './gps';\nexport function Screen() { return <Text>GPS</Text>; }\n")
        self.write("src/noise.ts", "export function unrelated() { return 'nothing'; }")

    def test_nine_heads_have_discoverable_executable_operations(self):
        self.assertEqual(len(HEADS), 9)
        for head in HEADS:
            for operation in head["operations"]:
                schema = self.suite.catalog(operation)
                self.assertEqual(schema["schema"]["additionalProperties"], False)

    def test_typescript_arrow_function_correct_braces(self):
        self.fixture()
        result = self.suite.query("snippet", {"path": "src/gps.ts", "symbol": "startGPS"})
        self.assertIn("getPosition();", result["text"])
        self.assertEqual(result["end"], 5)
        self.assertFalse(result["truncated"])
        self.assertFalse(result["syntax_errors"])

    def test_tsx_and_javascript_parsing(self):
        for path, text, name in [("a.tsx", "export const Card = () => <div>{42}</div>;", "Card"),
                                  ("b.js", "class X { run() { return '}'; } }", "X.run")]:
            self.write(path, text)
            result = self.suite.query("outline", {"path": path})
            self.assertIn(name, [s["qualified"] for s in result["symbols"]])
            self.assertFalse(result["syntax_errors"])

    def test_python_decorators_and_qualified_symbols(self):
        self.write("a.py", "class A:\n    @decorator\n    def run(self):\n        return 1\n")
        result = self.suite.query("snippet", {"path": "a.py", "symbol": "A.run"})
        self.assertEqual(result["start"], 2)
        self.assertIn("@decorator", result["text"])

    def test_invalid_syntax_is_not_reported_as_pass(self):
        self.write("bad.ts", "export function broken( { {{{")
        result = self.suite.query("verify", {"path": "bad.ts"})
        self.assertEqual(result["status"], "fail")

    def test_verify_does_not_execute_source(self):
        self.write("evil.js", "throw new Error('never run');")
        self.assertEqual(self.suite.query("verify", {"path": "evil.js"})["status"], "pass")

    def test_incremental_index_reparses_only_content_changes(self):
        self.fixture()
        self.assertEqual(self.suite.query("index")["reparsed"], 4)
        self.assertEqual(self.suite.query("index")["reparsed"], 0)
        self.write("src/location.ts", "export const location = 7;")
        self.assertEqual(self.suite.query("index")["reparsed"], 1)

    def test_index_removes_deleted_files_on_complete_refresh(self):
        self.fixture()
        self.suite.query("index")
        (self.root / "src/noise.ts").unlink()
        self.assertEqual(self.suite.query("index")["removed"], 1)

    def test_static_import_graph_reverse_depth(self):
        self.fixture()
        result = self.suite.query("impact", {"path": "src/location.ts", "depth": 2})
        self.assertEqual(result["importers"], ["src/gps.ts", "src/screen.tsx"])

    def test_unresolved_alias_is_explicit(self):
        self.write("a.ts", "import { gps } from '@/gps';\nexport function run() { return gps(); }")
        result = self.suite.query("impact", {"path": "a.ts"})
        self.assertIn("@/gps", result["unresolved_or_external_imports"])

    def test_context_packet_includes_dependencies_and_constraints(self):
        self.fixture()
        packet = self.suite.query("context", {"task": "Fix startGPS behavior", "paths": ["src/gps.ts"],
                                             "focus_symbols": {"src/gps.ts": "startGPS"}, "constraints": ["Keep Expo 52"]})
        self.assertIn("Keep Expo 52", packet["constraints"])
        self.assertTrue(any(i["path"] == "src/location.ts" for i in packet["items"]))
        self.assertTrue(any(i["path"] == "src/location.ts" and "return 42" in i["text"] for i in packet["items"]))
        self.assertTrue(any(i.get("symbol") == "startGPS" and "getPosition();" in i["text"] for i in packet["items"]))
        self.assertLessEqual(len(encode(packet).encode()), 12000)

    def test_packet_keeps_referenced_global_configuration(self):
        self.write("a.ts", "const gpsOptions = { distanceInterval: 1, timeInterval: 1000 };\nexport function startGPS() { return gpsOptions; }\n")
        packet = self.suite.query("context", {"task": "GPS", "paths": ["a.ts"], "focus_symbols": {"a.ts": "startGPS"}})
        self.assertTrue(any("distanceInterval: 1" in i["text"] for i in packet["items"]))

    def test_multiline_import_preserved(self):
        self.write("a.ts", "import {\n  x,\n  y\n} from './other';\nexport function main() { return x+y; }")
        packet = self.suite.query("context", {"task": "main", "paths": ["a.ts"], "focus_symbols": {"a.ts": "main"}})
        header = next(i for i in packet["items"] if i["kind"] == "import_statements")
        self.assertIn("} from './other';", header["text"])

    def test_packet_pinned_content_cannot_disappear_to_fit(self):
        self.fixture()
        with self.assertRaises(GuardError):
            self.suite.query("context", {"task": "GPS", "constraints": ["x" * 8000], "budget_bytes": 2048})

    def test_omitted_required_symbol_reports_incomplete(self):
        self.write("a.ts", "export function giant() {\n" + "const v = 1;\n" * 2000 + "}\n")
        packet = self.suite.query("context", {"task": "giant", "paths": ["a.ts"], "focus_symbols": {"a.ts": "giant"}, "budget_bytes": 2048})
        self.assertTrue(packet["coverage"]["incomplete"])
        self.assertIn("a.ts", packet["coverage"]["required_paths_missing"])

    def test_known_hash_reuse_is_explicit(self):
        self.fixture()
        digest = self.suite.guard.load("src/gps.ts")[2]
        packet = self.suite.query("context", {"task": "startGPS", "paths": ["src/gps.ts"], "known_hashes": {"src/gps.ts": digest}})
        self.assertFalse(any(i["path"] == "src/gps.ts" for i in packet["items"]))
        self.assertTrue(any(i["path"] == "src/gps.ts" for i in packet["deduplicated"]))

    def test_compress_deduplicates_exact_text_and_pins_constraints(self):
        result = self.suite.query("compress", {"blocks": [{"id": "a", "text": "Keep Expo 52", "pinned": True},
                                                              {"id": "b", "text": "Keep Expo 52"}, {"id": "c", "text": "noise" * 2000, "priority": 1}], "budget_bytes": 2048})
        self.assertEqual(result["blocks"][0]["text"], "Keep Expo 52")
        self.assertEqual(result["aliases"][0]["same_as"], "a")
        self.assertIn("c", result["omitted"])
        self.assertFalse(result["host_history_replaced"])

    def test_compress_rejects_duplicate_identifiers(self):
        with self.assertRaises(GuardError):
            self.suite.query("compress", {"blocks": [{"id": "a", "text": "one"}, {"id": "a", "text": "two"}]})

    def session(self, name="s", budget=12000, total=250000):
        return self.suite.manage("session_open", {"name": name, "call_budget_bytes": budget, "total_budget_bytes": total})

    def test_session_reopening_does_not_reset_spending(self):
        self.session()
        self.suite.query("plan", {"task": "GPS"}, session="s")
        self.assertGreater(self.session()["used_bytes"], 0)

    def test_total_budget_exhaustion_is_enforced(self):
        self.session(budget=2048, total=2048)
        for _ in range(2):
            self.suite.query("plan", {"task": "GPS"}, session="s")
        with self.assertRaises(GuardError):
            for _ in range(10):
                self.suite.query("plan", {"task": "GPS"}, session="s")
        self.suite.manage("session_close", {"name": "s"})
        with self.assertRaises(GuardError):
            self.suite.query("metrics", session="s")

    def test_atomic_budget_cannot_overspend_concurrently(self):
        self.session(budget=2048, total=2048)
        def query(_):
            try:
                self.suite.query("plan", {"task": "GPS"}, session="s")
                return True
            except GuardError:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(query, range(12)))
        policy = self.suite.state.session("s")
        self.assertLessEqual(policy["used"], policy["total_budget"])

    def test_delta_unchanged_and_changed_without_advancing_baseline(self):
        self.session()
        self.write("a.ts", "export const x = 1;\n")
        self.suite.manage("remember_read", {"path": "a.ts"}, session="s")
        self.assertTrue(self.suite.query("delta", {"path": "a.ts"}, session="s")["unchanged"])
        self.write("a.ts", "export const x = 2;\n")
        delta = self.suite.query("delta", {"path": "a.ts"}, session="s")
        self.assertIn("+export const x = 2;", delta["diff"])
        self.assertFalse(delta["baseline_advanced"])

    def test_missing_delta_baseline_and_session_are_explicit(self):
        self.session()
        self.write("a.ts", "const x = 1;")
        self.assertFalse(self.suite.query("delta", {"path": "a.ts"}, session="s")["baseline_available"])
        with self.assertRaises(GuardError):
            self.suite.query("delta", {"path": "a.ts"})

    def body(self):
        return {"goal": "Fix GPS", "constraints": [{"text": "Keep Expo 52", "source": "user"}],
                "decisions": [{"text": "Use native location", "source": "agent"}],
                "pending": ["Device test"], "files": ["src/gps.ts"], "validation": []}

    def test_memory_resume_checks_stale_files_and_preserves_constraints(self):
        self.fixture()
        self.suite.manage("memory_save", {"name": "gps", "body": self.body()})
        self.write("src/gps.ts", "export const changed = true;")
        resumed = self.suite.query("resume", {"name": "gps"})
        self.assertTrue(resumed["revalidation_required"])
        self.assertEqual(resumed["files"][0]["status"], "changed")
        packet = self.suite.query("context", {"task": "changed", "memory": "gps"})
        self.assertIn("Keep Expo 52", packet["constraints"])

    def test_memory_revision_conflict(self):
        self.fixture()
        self.suite.manage("memory_save", {"body": self.body()})
        with self.assertRaises(GuardError):
            self.suite.manage("memory_save", {"body": self.body()})

    def test_cache_sources_validated_and_invalidated(self):
        self.fixture()
        self.suite.manage("cache_save", {"key": "gps", "answer": "Use watchPosition", "files": ["src/gps.ts"]})
        self.assertTrue(self.suite.query("cache", {"key": "gps"})["hit"])
        self.write("src/gps.ts", "const changed = 1;")
        self.assertFalse(self.suite.query("cache", {"key": "gps"})["hit"])

    def test_logs_group_repetition_but_keep_status_codes_distinct(self):
        self.write("a.log", "2026-10-01T01:00:00Z ERROR HTTP 401 request 123456\n2026-10-01T01:00:01Z ERROR HTTP 401 request 123457\nERROR HTTP 500\nINFO hello\n")
        result = self.suite.query("logs", {"path": "a.log"})
        self.assertEqual(result["distinct_groups"], 2)
        self.assertEqual(result["groups"][0]["count"], 2)
        self.assertIn("401", result["groups"][0]["pattern"])

    def test_large_logs_stream_and_redact_credentials(self):
        self.write("a.log", "INFO normal\n" * 200000 + "ERROR token=secretvalue\n")
        result = self.suite.query("logs", {"path": "a.log"})
        self.assertGreater(result["bytes_scanned"], 2 * 1024 * 1024)
        self.assertNotIn("secretvalue", encode(result))

    def test_handoff_does_not_spawn_or_change_models(self):
        self.fixture()
        result = self.suite.query("handoff", {"task": "GPS", "role": "Reviewer", "constraints": ["Keep Expo 52"]})
        self.assertEqual(result["role"], "Reviewer")
        self.assertFalse(result["launches_agent"])
        self.assertFalse(result["changes_model"])

    def test_external_tool_route_does_not_modify_host(self):
        result = self.suite.query("route", {"task": "query SQL banco", "external_tools": [
            {"name": "sqlite.query", "tags": ["database", "sql"], "schema_bytes": 1000},
            {"name": "images", "tags": ["image"], "schema_bytes": 5000}]})
        self.assertEqual(result["suggested_external_tools"], ["sqlite.query"])
        self.assertFalse(result["changes_host_tool_loading"])

    def test_usage_deduplication_and_origin(self):
        usage = {"request_id": "r1", "provider": "Google", "model": "user-specified", "input_tokens": 100,
                 "output_tokens": 20, "cached_input_tokens": 30, "source": "provider_response"}
        self.suite.manage("usage_record", usage)
        self.assertTrue(self.suite.manage("usage_record", usage)["duplicate"])
        metrics = self.suite.query("metrics")
        self.assertEqual(metrics["reported_usage"]["requests"], 1)
        self.assertIsNone(metrics["automatic_provider_tokens"])
        usage["input_tokens"] = 80
        with self.assertRaises(GuardError):
            self.suite.manage("usage_record", usage)

    def test_evaluation_detects_quality_regression(self):
        trials = [{"task_id": "gps", "variant": "baseline", "input_tokens": 1000, "output_tokens": 50, "passed": True, "evidence": "device passed"},
                  {"task_id": "gps", "variant": "nexus", "input_tokens": 100, "output_tokens": 20, "passed": False, "evidence": "device failed"}]
        result = self.suite.query("evaluate", {"trials": trials})
        self.assertFalse(result["acceptable_on_supplied_checks"])
        self.assertEqual(result["quality_regressions"], ["gps"])

    def test_strict_operation_schema_rejects_unknowns_and_coercion(self):
        for params in ({"task": "GPS", "invented": True}, {"task": 42}):
            with self.assertRaises(GuardError):
                self.suite.query("plan", params)

    def test_secret_paths_cannot_enter_context_or_memory_sources(self):
        self.write(".env", "secret")
        with self.assertRaises(GuardError):
            self.suite.query("context", {"task": "secret", "paths": [".env"]})
        with self.assertRaises(GuardError):
            self.suite.manage("cache_save", {"key": "bad", "answer": "data", "files": [".env"]})


if __name__ == "__main__":
    unittest.main()
