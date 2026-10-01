import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

from nexus9.guard import Engine, GuardError, MAX_FILE_BYTES, encode, redact

CONFIGURE = Path(__file__).resolve().parents[1] / "configure.py"
spec = importlib.util.spec_from_file_location("configure", CONFIGURE)
configure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(configure)


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "project"
        self.root.mkdir()
        self.engine = Engine(self.root, self.base / "state")

    def write(self, name, text):
        file = self.root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")
        return file

    def test_root_is_explicit(self):
        with self.assertRaises(GuardError):
            Engine("relative")

    def test_traversal_and_absolute_paths(self):
        for path in ("../secret.txt", str(self.base / "outside.txt"), "C:/secret.txt", "x.txt:stream", "..\\secret.txt"):
            with self.subTest(path=path), self.assertRaises(GuardError):
                self.engine.read(path)

    def test_secret_paths_denied(self):
        for path in (".env", ".env.local", "credentials.json", "id_rsa", "key.pem", ".git/config", "node_modules/x.js"):
            self.write(path, "secret")
            with self.subTest(path=path), self.assertRaises(GuardError):
                self.engine.read(path)

    def test_symlinks_denied(self):
        target = self.base / "outside.txt"
        target.write_text("secret")
        try:
            (self.root / "linked.txt").symlink_to(target)
        except OSError:
            self.skipTest("symlink privilege unavailable")
        with self.assertRaises(GuardError):
            self.engine.read("linked.txt")

    def test_directory_symlinks_denied(self):
        try:
            (self.root / "linked").symlink_to(self.base, target_is_directory=True)
        except OSError:
            self.skipTest("symlink privilege unavailable")
        with self.assertRaises(GuardError):
            self.engine.inspect("linked")

    def test_hardlinks_denied(self):
        file = self.write("a.txt", "sensitive")
        try:
            os.link(file, self.root / "b.txt")
        except OSError:
            self.skipTest("hardlinks unavailable")
        with self.assertRaises(GuardError):
            self.engine.read("b.txt")

    def test_binary_non_utf8_and_large(self):
        for name, data in (("binary.txt", b"a\0b"), ("latin.txt", b"\xff"), ("big.txt", b"x" * (MAX_FILE_BYTES + 1))):
            (self.root / name).write_bytes(data)
            with self.subTest(name=name), self.assertRaises(GuardError):
                self.engine.read(name)

    def test_windows_backslash_relative_path(self):
        self.write("sub/a.py", "x = 1")
        self.assertEqual(self.engine.read("sub\\a.py")["lines"][0]["text"], "x = 1")

    def test_python_ast_decorators_and_strings(self):
        self.write("a.py", '@decorator\ndef wanted():\n    text = "} not a brace"\n    return text\n\ndef other():\n    return 1\n')
        result = self.engine.read("a.py", symbol="wanted")
        self.assertEqual(result["extraction"], "python_ast")
        self.assertEqual([x["line"] for x in result["lines"]], [1, 2, 3, 4])

    def test_symbol_ambiguity_and_qualified_lookup(self):
        self.write("a.py", "class A:\n    def run(self):\n        pass\nclass B:\n    def run(self):\n        pass\n")
        self.assertTrue(self.engine.read("a.py", symbol="run")["ambiguous"])
        self.assertEqual(self.engine.read("a.py", symbol="B.run")["lines"][0]["line"], 5)

    def test_non_python_never_claims_ast(self):
        self.write("a.ts", "const fn = () => { return 1; };\n")
        result = self.engine.read("a.ts", symbol="fn")
        self.assertEqual(result["extraction"], "literal_match_window_not_symbol_parser")

    def test_missing_symbol(self):
        self.write("a.py", "x = 1")
        self.assertFalse(self.engine.read("a.py", symbol="missing")["found"])

    def test_redaction_preserves_lines(self):
        text = "api_key = 'abcd'\nAuthorization: Bearer abc.xyz\n-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----\n"
        cleaned = redact(text)
        self.assertNotIn("abcd", cleaned)
        self.assertNotIn("abc.xyz", cleaned)
        self.assertNotIn("\nsecret\n", cleaned)
        self.assertEqual(text.count("\n"), cleaned.count("\n"))

    def test_redaction_before_window(self):
        self.write("a.txt", "-----BEGIN PRIVATE KEY-----\nsecretpayload\n-----END PRIVATE KEY-----\nnormal")
        result = self.engine.read("a.txt", start=2)
        self.assertNotIn("secretpayload", encode(result))

    def test_budget_includes_metadata_unicode(self):
        self.write("a.txt", ("é" * 600 + "\n") * 20)
        result = self.engine.read("a.txt", budget=1024)
        self.assertLessEqual(len(encode(result).encode()), 1024)
        self.assertTrue(result["truncated"])

    def test_long_line_reports_truncation(self):
        self.write("a.txt", "x" * 6000)
        self.assertTrue(self.engine.read("a.txt")["truncated"])

    def test_budget_pagination_never_skips_undelivered_lines(self):
        self.write("a.txt", ("line text " * 15 + "\n") * 100)
        result = self.engine.read("a.txt", count=100, budget=1024)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["next_line"], result["lines"][-1]["line"] + 1)
        resumed = self.engine.read("a.txt", start=result["next_line"], count=1)
        self.assertEqual(resumed["lines"][0]["line"], result["next_line"])

    def test_limits_and_types(self):
        self.write("a.py", "x=1")
        for kwargs in ({"count": 0}, {"count": True}, {"budget": 90000}, {"start": -1}, {"if_sha256": "bad"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(GuardError):
                self.engine.read("a.py", **kwargs)

    def test_cache_invalidates_same_size_same_mtime(self):
        file = self.write("a.txt", "first")
        first = self.engine.read("a.txt")
        self.assertTrue(self.engine.read("a.txt")["cache_hit"])
        info = file.stat()
        file.write_text("other")
        os.utime(file, ns=(info.st_atime_ns, info.st_mtime_ns))
        second = self.engine.read("a.txt")
        self.assertFalse(second["cache_hit"])
        self.assertNotEqual(first["sha256"], second["sha256"])

    def test_cache_expires(self):
        self.write("a.txt", "first")
        self.engine.read("a.txt")
        with self.engine.connect() as con:
            con.execute("UPDATE cache SET created=0")
        self.assertFalse(self.engine.read("a.txt")["cache_hit"])

    def test_conditional_read_explicit(self):
        self.write("a.txt", "first")
        first = self.engine.read("a.txt")
        second = self.engine.read("a.txt", if_sha256=first["sha256"])
        self.assertTrue(second["unchanged"])
        self.assertEqual(second["lines"], [])

    def test_namespaced_state(self):
        other = self.base / "other"
        other.mkdir()
        self.assertNotEqual(self.engine.db, Engine(other, self.base / "state").db)

    def test_search_is_literal_and_bounded(self):
        self.write("a.ts", "a+b\nA+B\naab\n")
        result = self.engine.search("a+b", limit=1)
        self.assertEqual(len(result["matches"]), 1)
        self.assertTrue(result["limited"])
        self.assertEqual(result["matches"][0]["line"], 1)

    def test_search_redacts(self):
        self.write("a.log", "error api_key='secretvalue'\n")
        self.assertNotIn("secretvalue", encode(self.engine.search("error")))

    def test_ignore_and_inventory(self):
        self.write(".nexusignore", "private/*\n")
        self.write("private/a.txt", "hidden")
        self.write("visible.txt", "shown")
        engine = Engine(self.root, self.base / "state")
        self.assertNotIn("private/a.txt", [x["path"] for x in engine.inspect()["files"]])
        with self.assertRaises(GuardError):
            engine.read("private/a.txt")

    def test_syntax_checks_never_execute(self):
        self.write("evil.py", "raise RuntimeError('never execute')")
        self.assertEqual(self.engine.inspect("evil.py", "syntax")["status"], "pass")
        self.write("bad.py", "def broken(:")
        self.assertEqual(self.engine.inspect("bad.py", "syntax")["status"], "fail")
        self.write("bad.json", "{")
        self.assertEqual(self.engine.inspect("bad.json", "syntax")["status"], "fail")
        self.write("bad.ts", "invalid {{{")
        self.assertEqual(self.engine.inspect("bad.ts", "syntax")["status"], "unsupported")

    def test_nonfinite_json_is_rejected(self):
        self.write("bad.json", '{"value":NaN}')
        self.assertEqual(self.engine.inspect("bad.json", "syntax")["status"], "fail")
        config = self.base / "mcp.json"
        config.write_text('{"value":Infinity}')
        with self.assertRaises(ValueError):
            configure.merge(config, "contextguard", {})

    def body(self):
        return {"objective": "Fix bug", "decisions": [], "pending": ["compile"], "files": ["a.ts"], "validation": []}

    def test_checkpoint_revision_conflicts(self):
        self.assertFalse(self.engine.checkpoint("get")["found"])
        self.assertEqual(self.engine.checkpoint("save", body=self.body())["revision"], 1)
        with self.assertRaises(GuardError):
            self.engine.checkpoint("save", body=self.body())
        self.assertEqual(self.engine.checkpoint("save", body=self.body(), expected_revision=1)["revision"], 2)

    def test_checkpoint_survives_restart_and_redacts(self):
        body = self.body()
        body["decisions"] = ["token=supersecret"]
        self.engine.checkpoint("save", body=body)
        restarted = Engine(self.root, self.base / "state")
        self.assertNotIn("supersecret", encode(restarted.checkpoint("get")))

    def test_checkpoint_validation(self):
        for body in ({}, {**self.body(), "pending": "wrong"}, {**self.body(), "objective": "x" * 10001}):
            with self.subTest(body=type(body)), self.assertRaises(GuardError):
                self.engine.checkpoint("save", body=body)

    def test_concurrent_checkpoint_updates(self):
        self.engine.checkpoint("save", body=self.body())
        def update(_):
            try:
                self.engine.checkpoint("save", body=self.body(), expected_revision=1)
                return "ok"
            except GuardError:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(update, range(2)))
        self.assertEqual(sorted(outcomes), ["conflict", "ok"])

    def test_metrics_do_not_invent_billing(self):
        self.write("a.txt", "a")
        self.engine.read("a.txt")
        result = self.engine.metrics()
        self.assertEqual(result["calls"], 1)
        self.assertIsNone(result["actual_provider_tokens"])
        self.assertIsNone(result["actual_cost"])

    def test_config_atomic_preservation_idempotency_and_backup(self):
        config = self.base / "mcp.json"
        original = b'{"extra":true,"mcpServers":{"existing":{"command":"node"}}}'
        config.write_bytes(original)
        backup = configure.merge(config, "contextguard", {"command": "python"})
        self.assertEqual(backup.read_bytes(), original)
        self.assertTrue(json.loads(config.read_text())["extra"])
        self.assertIn("existing", json.loads(config.read_text())["mcpServers"])
        self.assertIsNone(configure.merge(config, "contextguard", {"command": "python"}))

    def test_config_invalid_json_or_duplicate_keys_untouched(self):
        config = self.base / "mcp.json"
        for original in (b'{bad', b'{"mcpServers":{},"mcpServers":{}}'):
            config.write_bytes(original)
            with self.assertRaises(ValueError):
                configure.merge(config, "contextguard", {})
            self.assertEqual(config.read_bytes(), original)

    def test_config_conflict_untouched(self):
        config = self.base / "mcp.json"
        config.write_text('{"mcpServers":{"contextguard":{"command":"old"}}}')
        original = config.read_bytes()
        with self.assertRaises(ValueError):
            configure.merge(config, "contextguard", {"command": "new"})
        self.assertEqual(config.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
