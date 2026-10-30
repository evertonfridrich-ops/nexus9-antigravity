"""Opt-in execution of trusted Python unittest profiles with observed receipts.

No MCP argument supplies an executable, command, environment or shell fragment.
The runner is not an OS sandbox: trusted tests execute with the server user's
permissions and can access network/files outside the snapshot. Source hashes
cover the allowlist, test-tree Python files and explicitly supplied dependencies.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import threading
import time
from uuid import uuid4

from pydantic import ValidationError

from .check_models import CheckConfiguration, CheckRun
from .guard import GuardError, encode, redact

CONFIG = "nexus9-checks.json"
OUTPUT_BYTES = 8192
MAX_SOURCES = 100
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_RUNS = 100
SUMMARY = re.compile(r"(?m)^Ran ([0-9]+) tests? in [0-9.]+s\s*$")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError("non-finite JSON value")


def _digest(value):
    return hashlib.sha256(encode(value).encode("utf-8")).hexdigest()


class CheckRunner:
    def __init__(self, guard, enabled=False):
        self.guard = guard
        self.enabled = enabled
        with guard.connect() as con:
            con.execute("CREATE TABLE IF NOT EXISTS check_runs (run_id TEXT PRIMARY KEY, body TEXT NOT NULL)")

    def _configuration(self):
        try:
            if self.guard.path(CONFIG).stat().st_size > 16384:
                raise GuardError("test profile configuration exceeds 16 KiB")
            _, raw, sha, size = self.guard.load(CONFIG)
            if size > 16384:
                raise GuardError("test profile configuration exceeds 16 KiB")
            body = json.loads(raw, object_pairs_hook=_unique, parse_constant=_invalid_constant)
            parsed = CheckConfiguration.model_validate(body)
        except (OSError, ValueError, RecursionError, ValidationError):
            raise GuardError("test profile configuration unavailable or invalid") from None
        return parsed.profiles, sha

    def profiles(self):
        if not self.enabled:
            return {"enabled": False, "profiles": [], "reason": "test runner requires explicit server opt-in"}
        profiles, sha = self._configuration()
        return {"enabled": True, "configuration_sha256": sha,
                "profiles": [{"name": name, "kind": profile.kind} for name, profile in sorted(profiles.items())],
                "execution_scope": "trusted project tests with user OS permissions; no network isolation"}

    def _test_files(self, start_dir):
        base = self.guard.path(start_dir, directory=True)
        entries = 0
        started = time.monotonic()
        pending = [base]
        paths = set()
        # unittest may import package initializers above its start directory.
        current = base.parent
        while current.is_relative_to(self.guard.root):
            initializer = current / "__init__.py"
            if os.path.lexists(initializer):
                paths.add(initializer.relative_to(self.guard.root).as_posix())
            if current == self.guard.root:
                break
            current = current.parent
        while pending:
            directory = pending.pop()
            try:
                with os.scandir(directory) as scan:
                    for entry in scan:
                        entries += 1
                        if entries > 1000 or time.monotonic() - started > 3:
                            raise GuardError("test tree inventory exceeds bounded scan limits")
                        info = entry.stat(follow_symlinks=False)
                        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                            raise GuardError("test tree contains a link or reparse point")
                        if entry.name == "__pycache__":
                            continue
                        if stat.S_ISDIR(info.st_mode):
                            pending.append(Path(entry.path))
                        elif entry.name.endswith(".py"):
                            paths.add(Path(entry.path).relative_to(self.guard.root).as_posix())
                        if len(paths) + 1 > MAX_SOURCES:
                            raise GuardError("test source inventory exceeds 100 files")
            except OSError:
                raise GuardError("test tree unavailable") from None
        return sorted(paths)

    def _snapshot(self, profile, sources, config_sha):
        test_files = self._test_files(profile.start_dir)
        paths = set(sources) | set(test_files)
        fingerprints = {CONFIG: config_sha}
        total_bytes = 0
        for path in sorted(paths):
            source, _, sha, size = self.guard.load(path)
            canonical = source.relative_to(self.guard.root).as_posix()
            fingerprints[canonical] = sha
            total_bytes += size
            if total_bytes > MAX_SOURCE_BYTES or len(fingerprints) > MAX_SOURCES:
                raise GuardError("test source inventory exceeds bounded size")
        return fingerprints, test_files

    def _fresh(self, hashes, test_scope=None):
        changed = []
        for path, previous in hashes.items():
            try:
                _, _, current, _ = self.guard.load(path)
                if previous != current:
                    changed.append(path)
            except (GuardError, OSError):
                changed.append(path)
        if test_scope is not None:
            try:
                current_files = self._test_files(test_scope["start_dir"])
                if current_files != test_scope["files"]:
                    changed.extend(sorted(set(current_files) ^ set(test_scope["files"])))
            except (GuardError, OSError):
                changed.append(test_scope["start_dir"])
        changed = sorted(set(changed))
        return not changed, changed

    @staticmethod
    def _environment():
        # Keep only runtime essentials; do not forward project API keys/tokens.
        allowed = ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "TEMP", "TMP", "HOME", "USERPROFILE")
        result = {key: value for key, value in os.environ.items() if key.upper() in allowed}
        result.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
        return result

    @staticmethod
    def _stop(process):
        if os.name == "nt":
            system = os.environ.get("SystemRoot", r"C:\Windows")
            try:
                subprocess.run([str(Path(system) / "System32" / "taskkill.exe"), "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3, shell=False)
            except (OSError, subprocess.TimeoutExpired):
                pass
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass

    def _execute(self, profile):
        command = [sys.executable, "-I", "-B", "-X", "utf8", "-m", "unittest", "discover", "-s", profile.start_dir,
                   "-t", str(self.guard.root), "-p", profile.pattern]
        options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        process = subprocess.Popen(command, cwd=self.guard.root, env=self._environment(), shell=False,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **options)
        capture = bytearray()
        count = [0]

        def consume():
            try:
                while True:
                    chunk = process.stdout.read(4096)
                    if not chunk:
                        break
                    count[0] += len(chunk)
                    capture.extend(chunk)
                    if len(capture) > OUTPUT_BYTES:
                        del capture[:-OUTPUT_BYTES]
            except OSError:
                pass

        reader = threading.Thread(target=consume, daemon=True)
        reader.start()
        timed_out = False
        try:
            process.wait(timeout=profile.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._stop(process)
        reader.join(timeout=1)
        complete = not reader.is_alive()
        if complete:
            process.stdout.close()
        data = bytes(capture)
        truncated = count[0] > OUTPUT_BYTES
        if truncated:
            # Drop a partial first line before redaction, so truncation cannot
            # remove an assignment/key prefix while retaining its value.
            data = data.split(b"\n", 1)[1] if b"\n" in data else b""
        output = redact(data.decode("utf-8", errors="replace"))
        while len(output.encode("utf-8")) > OUTPUT_BYTES:
            output = output[1:]
            truncated = True
        counts = SUMMARY.findall(output)
        tests_run = int(counts[-1]) if counts else None
        footers = re.findall(r"(?m)^OK(?:\s*\(([^\r\n]*)\))?\s*$", output)
        footer = footers[-1] if footers else ""
        skipped_match = re.search(r"(?:^|,\s*)skipped=([0-9]+)", footer)
        expected_match = re.search(r"(?:^|,\s*)expected failures=([0-9]+)", footer)
        tests_skipped = int(skipped_match[1]) if skipped_match else 0
        tests_expected_failures = int(expected_match[1]) if expected_match else 0
        tests_executed = max(0, tests_run - tests_skipped) if tests_run is not None else None
        tests_passed = max(0, tests_executed - tests_expected_failures) if tests_executed is not None else None
        passed = (not timed_out and complete and process.returncode == 0 and tests_run is not None
                  and tests_passed > 0 and bool(footers))
        return {"exit_code": process.returncode, "tests_run": tests_run, "timed_out": timed_out,
                "tests_skipped": tests_skipped, "tests_executed": tests_executed,
                "tests_expected_failures": tests_expected_failures, "tests_passed": tests_passed,
                "output": output, "output_truncated": truncated, "output_complete": complete,
                "passed": passed, "status": "passed" if passed else "timeout" if timed_out else
                "no_tests" if tests_run == 0 else "no_executed_tests" if tests_executed == 0 else
                "no_passing_tests" if tests_passed == 0 and footers else "failed"}

    def run(self, profile, sources=None):
        if not self.enabled:
            raise GuardError("test runner disabled; restart server with explicit test-runner opt-in")
        try:
            values = CheckRun.model_validate({"profile": profile, "sources": sources if sources is not None else []})
        except ValidationError:
            raise GuardError("invalid test runner parameters") from None
        profiles, config_sha = self._configuration()
        if values.profile not in profiles:
            raise GuardError("unknown test profile")
        selected = profiles[values.profile]
        hashes, test_files = self._snapshot(selected, values.sources, config_sha)
        run_id = "run_" + uuid4().hex
        original = {"run_id": run_id, "profile": values.profile, "source_hashes": hashes,
                    "test_scope": {"start_dir": selected.start_dir, "files": test_files},
                    "provenance": "nexus9_observed_process", "status": "running", "passed": False,
                    "recorded_at": time.time(), "scope": "trusted Python unittest process; explicit dependencies and test-tree snapshot, no OS sandbox"}
        with self.guard.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT count(*) FROM check_runs").fetchone()[0] >= MAX_RUNS:
                raise GuardError("test run capacity reached (100); existing evidence receipts are retained")
            con.execute("INSERT INTO check_runs VALUES(?,?)", (run_id, encode(original)))
        try:
            observed = self._execute(selected)
        except OSError:
            observed = {"status": "start_failed", "passed": False, "exit_code": None,
                        "tests_run": None, "timed_out": False, "output": "", "output_truncated": False,
                        "output_complete": False}
        fresh, changed = self._fresh(hashes, original["test_scope"])
        original.update(observed)
        original["source_changed_during_run"] = changed
        if not fresh:
            original.update(passed=False, status="source_changed")
        original["receipt_sha256"] = _digest(original)
        with self.guard.connect() as con:
            con.execute("UPDATE check_runs SET body=? WHERE run_id=?", (encode(original), run_id))
        return self.get_run(run_id)

    def get_run(self, run_id):
        with self.guard.connect() as con:
            row = con.execute("SELECT body FROM check_runs WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            raise GuardError("test run not found")
        receipt = json.loads(row[0])
        fresh, changed = self._fresh(receipt["source_hashes"], receipt.get("test_scope"))
        recorded_passed = receipt["passed"]
        receipt.update(fresh=fresh, changed_sources=changed, recorded_passed=recorded_passed,
                       passed=bool(recorded_passed and fresh))
        if not fresh:
            receipt["recorded_status"] = receipt["status"]
            receipt["status"] = "needs_revalidation"
        return receipt
