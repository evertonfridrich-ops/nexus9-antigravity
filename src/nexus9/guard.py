from __future__ import annotations

import ast
from contextlib import contextmanager
import fnmatch
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
from typing import Any

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_BYTES = 24 * 1024
MAX_ENTRIES = 5000
SCAN_SECONDS = 3.0
EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__",
    "dist", "build", ".next", ".expo", ".nexus9", ".idea",
}
DENIED_NAMES = {"credentials.json", "credentials", "id_rsa", "id_ed25519", ".npmrc", ".pypirc"}
DENIED_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".sqlite", ".sqlite3", ".db"}
TEXT_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".md", ".txt", ".log",
    ".yml", ".yaml", ".toml", ".ini", ".css", ".scss", ".html", ".xml",
    ".java", ".kt", ".kts", ".c", ".h", ".cpp", ".rs", ".go", ".sh",
    ".ps1", ".sql", ".gradle", ".properties", ".dart", ".swift",
}
PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)
ASSIGNMENT = re.compile(
    r'''(?im)(?<![\w.-])((?:["']?)(?:[\w.-]*(?:api[_-]?key|password|passwd|secret|token)[\w.-]*)(?:["']?)\s*[:=]\s*)(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;\r\n]+)'''
)
BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_.~+/=-]+")
KNOWN_KEY = re.compile(r"\b(?:AIza[A-Za-z0-9_-]{25,}|gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})\b")


class GuardError(ValueError):
    """A bounded, safe diagnostic suitable for the MCP caller."""


def redact(text: str) -> str:
    text = PRIVATE_KEY.sub(lambda m: "[REDACTED PRIVATE KEY]" + "\n" * m[0].count("\n"), text)
    text = ASSIGNMENT.sub(lambda m: m[1] + '"[REDACTED]"', text)
    text = BEARER.sub("Bearer [REDACTED]", text)
    return KNOWN_KEY.sub("[REDACTED KEY]", text)


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def bounded(value: dict, budget: int = MAX_OUTPUT_BYTES) -> dict:
    """Bound the full serialized result, including metadata; never cut JSON mid-byte."""
    value = dict(value)
    if len(encode(value).encode()) <= budget:
        return value
    value["truncated"] = True
    for key in ("lines", "matches", "files", "candidates", "items"):
        while value.get(key) and len(encode(value).encode()) > budget:
            value[key].pop()
    if len(encode(value).encode()) > budget:
        return {"truncated": True, "reason": "metadata_exceeds_output_budget"}
    return value


def integer(value: int, low: int, high: int, name: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise GuardError(f"{name} must be an integer between {low} and {high}")
    return value


def reject_constant(value):
    raise ValueError("non-finite JSON value")


class Engine:
    def __init__(self, root: str | Path, state_dir: str | Path | None = None):
        requested = Path(root).expanduser()
        if not requested.is_absolute() or not requested.is_dir():
            raise GuardError("workspace root must be an existing absolute directory")
        self.root = requested.resolve(strict=True)
        self.namespace = hashlib.sha256(os.fsencode(self.root)).hexdigest()[:24]
        base = Path(state_dir) if state_dir else Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "state")) / "Nexus9"
        self.state = base.expanduser().resolve() / self.namespace
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            self.state.chmod(0o700)
        self.db = self.state / "state.sqlite3"
        with self.connect() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, created REAL, result TEXT);
                CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, at REAL, tool TEXT,
                    status TEXT, duration_ms REAL, output_bytes INTEGER, input_bytes INTEGER, cache_hit INTEGER);
                CREATE TABLE IF NOT EXISTS checkpoints (name TEXT PRIMARY KEY, revision INTEGER,
                    updated REAL, body TEXT);
            """)
        if os.name != "nt":
            self.db.chmod(0o600)
        self.ignore = []
        ignore = self.root / ".nexusignore"
        if ignore.exists() and not ignore.is_symlink() and ignore.is_file() and ignore.stat().st_size <= 16384:
            self.ignore = [x.strip() for x in ignore.read_text(encoding="utf-8").splitlines()
                           if x.strip() and not x.lstrip().startswith("#")]

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.db, timeout=5)
        try:
            con.execute("PRAGMA busy_timeout=5000")
            with con:
                yield con
        finally:
            con.close()

    def allowed(self, relative: Path) -> bool:
        parts = [p.lower() for p in relative.parts]
        name = relative.name.lower()
        return not (
            any(p in EXCLUDED_DIRS for p in parts)
            or name.startswith(".env") or name in DENIED_NAMES
            or relative.suffix.lower() in DENIED_SUFFIXES
            or any(fnmatch.fnmatch(relative.as_posix(), pattern) for pattern in self.ignore)
        )

    def path(self, value: str, directory: bool = False) -> Path:
        if not isinstance(value, str) or not value or len(value) > 4096 or "\x00" in value:
            raise GuardError("invalid path")
        # Accept only relative paths; reject alternate data streams and drive/UNC paths.
        if "\\" in value:
            value = value.replace("\\", "/")
        rel = Path(value)
        if rel.is_absolute() or ":" in value or ".." in rel.parts:
            raise GuardError("only workspace-relative paths without traversal are allowed")
        if not self.allowed(rel):
            raise GuardError("path denied by workspace policy")
        candidate = self.root / rel
        current = self.root
        for part in rel.parts:
            current = current / part
            try:
                info = current.lstat()
            except OSError:
                raise GuardError("path unavailable") from None
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise GuardError("symlinks and Windows reparse points are denied")
        try:
            candidate.resolve(strict=True).relative_to(self.root)
            info = candidate.stat()
        except (OSError, ValueError):
            raise GuardError("path unavailable or outside workspace") from None
        if directory:
            if not stat.S_ISDIR(info.st_mode):
                raise GuardError("directory required")
        elif not stat.S_ISREG(info.st_mode) or info.st_nlink > 1:
            raise GuardError("only regular, singly-linked files are allowed")
        return candidate

    def load(self, value: str) -> tuple[Path, str, str, int]:
        path = self.path(value)
        if path.stat().st_size > MAX_FILE_BYTES:
            raise GuardError("file exceeds 2 MiB; split or filter it outside this server")
        # No shell, execution or follow-links for the final component on POSIX.
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1:
                raise GuardError("unsafe file type")
            data = stream.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES or b"\x00" in data:
            raise GuardError("oversized or binary file denied")
        try:
            text = data.decode("utf-8-sig")
        except UnicodeError:
            raise GuardError("file must be UTF-8 text") from None
        return path, text, hashlib.sha256(data).hexdigest(), len(data)

    def walk(self, directory: str = ".", max_entries: int = MAX_ENTRIES, seconds: float = SCAN_SECONDS):
        base = self.path(directory, directory=True)
        start, visited = time.monotonic(), 0
        self.scan_limited = False
        stack = [base]
        while stack:
            folder = stack.pop()
            try:
                # Stream directory entries instead of materializing unbounded listings.
                with os.scandir(folder) as entries:
                    for entry in entries:
                        visited += 1
                        if visited > max_entries or time.monotonic() - start > seconds:
                            self.scan_limited = True
                            return
                        rel = Path(entry.path).relative_to(self.root)
                        if not self.allowed(rel) or entry.is_symlink():
                            continue
                        info = entry.stat(follow_symlinks=False)
                        if getattr(info, "st_file_attributes", 0) & 0x400:
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False) and info.st_nlink == 1:
                            if info.st_size <= MAX_FILE_BYTES and (rel.suffix.lower() in TEXT_SUFFIXES or rel.name.lower() in {"dockerfile", "makefile"}):
                                yield rel.as_posix(), info.st_size
            except OSError:
                continue

    def record(self, tool: str, status: str, started: float, result: dict,
               input_bytes: int = 0, cache_hit: bool = False):
        with self.connect() as con:
            con.execute("INSERT INTO events(at,tool,status,duration_ms,output_bytes,input_bytes,cache_hit) VALUES(?,?,?,?,?,?,?)",
                        (time.time(), tool, status, (time.monotonic() - started) * 1000,
                         len(encode(result).encode()), input_bytes, int(cache_hit)))
            con.execute("DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 10000)")

    def read(self, path: str, start: int = 1, count: int = 80, symbol: str = "",
             if_sha256: str = "", budget: int = 12000) -> dict:
        integer(start, 1, 1000000, "start")
        integer(count, 1, 300, "count")
        integer(budget, 1024, MAX_OUTPUT_BYTES, "budget")
        if not isinstance(symbol, str) or len(symbol) > 200:
            raise GuardError("symbol must have at most 200 characters")
        if if_sha256 and not re.fullmatch(r"[0-9a-f]{64}", if_sha256):
            raise GuardError("if_sha256 must be a lowercase SHA-256 digest")
        started = time.monotonic()
        file, raw, digest, size = self.load(path)
        info = {"path": file.relative_to(self.root).as_posix(), "sha256": digest,
                "source_bytes": size, "estimate": {"method": "UTF-8 bytes / 4 heuristic", "tokens": math.ceil(size / 4), "exact": False},
                "content_is_untrusted": True, "truncated": False}
        if if_sha256 == digest:
            result = {**info, "unchanged": True, "lines": [], "note": "Reuse only if this digest's content remains in your active context."}
            self.record("read", "ok", started, result, size)
            return result
        key = hashlib.sha256(encode([info["path"], digest, start, count, symbol, budget, 1]).encode()).hexdigest()
        with self.connect() as con:
            cached = con.execute("SELECT result FROM cache WHERE key=? AND created>?", (key, time.time() - 3600)).fetchone()
        if cached:
            result = json.loads(cached[0])
            result["cache_hit"] = True
            result = bounded(result, budget)
            self.record("read", "ok", started, result, size, True)
            return result
        # Redact the entire source first, so multiline private keys cannot leak through a window.
        lines = redact(raw).splitlines()
        info["total_lines"] = len(lines)
        if symbol:
            if file.suffix == ".py":
                try:
                    tree = ast.parse(raw)
                except SyntaxError:
                    raise GuardError("cannot extract Python symbol from invalid syntax") from None
                matches = []
                def visit(node, parent=""):
                    for child in ast.iter_child_nodes(node):
                        if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                            qualified = f"{parent}.{child.name}" if parent else child.name
                            if symbol in (qualified, child.name):
                                matches.append((qualified, child))
                            visit(child, qualified)
                        else:
                            visit(child, parent)
                visit(tree)
                if len(matches) != 1:
                    result = bounded({**info, "symbol": symbol, "found": bool(matches), "ambiguous": len(matches) > 1,
                                      "candidates": [m[0] for m in matches][:50]}, budget)
                    self.record("read", "ok", started, result, size)
                    return result
                node = matches[0][1]
                start = min([node.lineno] + [d.lineno for d in node.decorator_list])
                end = node.end_lineno or start
                info["extraction"] = "python_ast"
                # Line numbers can shift when redaction removes a multiline key.
                if len(lines) != len(raw.splitlines()):
                    raise GuardError("multiline secret redaction prevents reliable symbol line mapping")
            else:
                hits = [i + 1 for i, line in enumerate(lines) if symbol in line]
                if not hits:
                    result = {**info, "symbol": symbol, "found": False}
                    self.record("read", "ok", started, result, size)
                    return result
                start = max(1, hits[0] - 5)
                end = start + count - 1
                info["extraction"] = "literal_match_window_not_symbol_parser"
                info["matching_lines"] = hits[:50]
        else:
            end = start + count - 1
            info["extraction"] = "line_window"
        last = min(end, start + count - 1, len(lines))
        selected = [{"line": i + 1, "text": lines[i][:4096]} for i in range(start - 1, last)]
        info["truncated"] = last < min(end, len(lines)) or any(len(lines[i]) > 4096 for i in range(start - 1, last))
        result = bounded({**info, "lines": selected, "cache_hit": False, "next_line": last + 1}, budget)
        result["next_line"] = (result["lines"][-1]["line"] + 1) if result.get("lines") else start
        with self.connect() as con:
            con.execute("INSERT OR REPLACE INTO cache VALUES(?,?,?)", (key, time.time(), encode(result)))
            con.execute("DELETE FROM cache WHERE key NOT IN (SELECT key FROM cache ORDER BY created DESC LIMIT 256)")
        self.record("read", "ok", started, result, size)
        return result

    def search(self, query: str, directory: str = ".", limit: int = 30, budget: int = 12000) -> dict:
        if not isinstance(query, str) or not 1 <= len(query) <= 200 or "\n" in query or "\r" in query:
            raise GuardError("query must be a single line of 1 to 200 characters")
        integer(limit, 1, 100, "limit")
        integer(budget, 1024, MAX_OUTPUT_BYTES, "budget")
        started, matches, scanned, source_bytes, stopped = time.monotonic(), [], 0, 0, False
        for rel, _ in self.walk(directory):
            if time.monotonic() - started > SCAN_SECONDS:
                stopped = True
                break
            try:
                _, raw, _, size = self.load(rel)
            except (GuardError, OSError):
                continue
            scanned += 1
            source_bytes += size
            for number, line in enumerate(redact(raw).splitlines(), 1):
                if query.casefold() in line.casefold():
                    matches.append({"path": rel, "line": number, "text": line[:500]})
                    if len(matches) == limit:
                        stopped = True
                        break
            if stopped:
                break
        result = bounded({"matches": matches, "files_scanned": scanned, "limited": stopped or self.scan_limited,
                          "search": "literal_case_insensitive_not_dependency_graph", "content_is_untrusted": True}, budget)
        self.record("search", "ok", started, result, source_bytes)
        return result

    def inspect(self, path: str = ".", mode: str = "inventory", max_bytes: int = MAX_FILE_BYTES) -> dict:
        started = time.monotonic()
        if mode == "inventory":
            files, count = [], 0
            for rel, size in self.walk(path):
                count += 1
                files.append({"path": rel, "bytes": size})
                files.sort(key=lambda x: (-x["bytes"], x["path"]))
                del files[50:]
            result = bounded({"files": files, "eligible_files": count, "limited": self.scan_limited,
                              "policy": "curated exclusions + .nexusignore globs; not full gitignore"})
            self.record("inspect", "ok", started, result)
            return result
        file, raw, digest, size = self.load(path)
        if size > max_bytes:
            raise GuardError("source exceeds hardware profile file limit")
        result = {"path": file.relative_to(self.root).as_posix(), "sha256": digest, "bytes": size}
        if mode == "syntax":
            try:
                if file.suffix == ".py":
                    ast.parse(raw)
                    result.update(status="pass", scope="Python syntax only; no execution")
                elif file.suffix == ".json":
                    json.loads(raw, parse_constant=reject_constant)
                    result.update(status="pass", scope="JSON syntax only; no schema validation")
                else:
                    result.update(status="unsupported", scope="Run the project's actual compiler or tests for this language")
            except (SyntaxError, json.JSONDecodeError) as err:
                result.update(status="fail", line=err.lineno, message="invalid syntax")
            except ValueError:
                result.update(status="fail", message="non-finite values are not valid JSON")
        elif mode != "fingerprint":
            raise GuardError("unknown inspect mode")
        self.record("inspect", "ok", started, result, size)
        return result

    def checkpoint(self, action: str, name: str = "default", body: dict | None = None,
                   expected_revision: int = 0) -> dict:
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
            raise GuardError("checkpoint name must be 1 to 64 letters, digits, underscores or hyphens")
        integer(expected_revision, 0, 1000000000, "expected_revision")
        started = time.monotonic()
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT revision,updated,body FROM checkpoints WHERE name=?", (name,)).fetchone()
            if action == "get":
                result = {"name": name, "found": bool(row)}
                if row:
                    result.update(revision=row[0], updated=row[1], body=json.loads(row[2]), content_is_untrusted=True)
            elif action == "save":
                if not isinstance(body, dict) or set(body) != {"objective", "decisions", "pending", "files", "validation"}:
                    raise GuardError("body requires exactly objective, decisions, pending, files, validation")
                if not isinstance(body["objective"], str) or any(not isinstance(body[k], list) or any(not isinstance(x, str) for x in body[k])
                       for k in ("decisions", "pending", "files", "validation")):
                    raise GuardError("objective must be text; other fields must be lists of text")
                text = encode(body)
                if len(text.encode()) > 10000:
                    raise GuardError("checkpoint exceeds 10000 UTF-8 bytes")
                clean = {k: redact(v) if isinstance(v, str) else [redact(x) for x in v] for k, v in body.items()}
                revision = row[0] if row else 0
                if revision != expected_revision:
                    raise GuardError(f"revision conflict; current revision is {revision}")
                if not row and con.execute("SELECT count(*) FROM checkpoints").fetchone()[0] >= 100:
                    raise GuardError("checkpoint capacity reached (100)")
                con.execute("INSERT OR REPLACE INTO checkpoints VALUES(?,?,?,?)", (name, revision + 1, time.time(), encode(clean)))
                result = {"name": name, "revision": revision + 1, "saved": True,
                          "note": "Persistent state only; this does not replace the host conversation."}
            else:
                raise GuardError("checkpoint action must be get or save")
        self.record("checkpoint", "ok", started, result)
        return result

    def metrics(self) -> dict:
        with self.connect() as con:
            total = con.execute("SELECT count(*),coalesce(sum(output_bytes),0),coalesce(sum(input_bytes),0),coalesce(sum(cache_hit),0) FROM events").fetchone()
            tools = con.execute("SELECT tool,count(*),round(avg(duration_ms),2) FROM events GROUP BY tool").fetchall()
            cache_count = con.execute("SELECT count(*) FROM cache WHERE created>?", (time.time() - 3600,)).fetchone()[0]
        return {"window": "last 10000 local tool events", "calls": total[0], "core_result_bytes": total[1],
                "source_bytes_processed": total[2], "cache_hits": total[3], "live_cache_entries": cache_count,
                "tools": [{"tool": r[0], "calls": r[1], "mean_ms": r[2]} for r in tools],
                "actual_provider_tokens": None, "actual_cost": None,
                "note": "Local result sizes exclude MCP envelope and host/tool-schema overhead; not billing or proven savings."}
