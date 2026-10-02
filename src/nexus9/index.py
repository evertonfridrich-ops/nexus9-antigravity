"""Incremental lexical index and parser-backed outlines, not a type checker."""
from __future__ import annotations

import ast
from collections import Counter
import json
import math
from pathlib import PurePosixPath
import posixpath
import re
import time

from tree_sitter import Language, Parser
import tree_sitter_javascript
import tree_sitter_typescript
import tree_sitter_python

from .guard import Engine, GuardError, redact, encode
from .policy import RuntimePolicy

LANGUAGES = {
    ".py": Language(tree_sitter_python.language()),
    ".js": Language(tree_sitter_javascript.language()),
    ".jsx": Language(tree_sitter_javascript.language()),
    ".ts": Language(tree_sitter_typescript.language_typescript()),
    ".tsx": Language(tree_sitter_typescript.language_tsx()),
}


def terms(text: str) -> list[str]:
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return [x for x in re.findall(r"[a-z0-9_]+", text.casefold()) if 2 <= len(x) <= 64]


def outline(path: str, raw: str) -> dict:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix not in LANGUAGES:
        return {"language": "text", "parsed": False, "syntax_errors": None, "symbols": [], "imports": [], "import_ranges": []}
    source = raw.encode("utf-8")
    source_lines = raw.splitlines()
    tree = Parser(LANGUAGES[suffix]).parse(source)
    stack, symbols, imports, import_ranges, visited = [(tree.root_node, "")], [], [], [], 0
    references = {}
    function_types = {"function_declaration", "function_definition", "class_declaration", "class_definition",
                      "method_definition", "method_signature", "interface_declaration", "type_alias_declaration", "enum_declaration"}
    while stack:
        node, scope = stack.pop()
        visited += 1
        if visited > 100000:
            break
        next_scope = scope
        name_node = node.child_by_field_name("name")
        named = node.type in function_types
        if node.type == "variable_declarator":
            value = node.child_by_field_name("value")
            named = value is not None and (not scope or value.type in {"arrow_function", "function_expression", "class"})
        if named and name_node is not None:
            name = source[name_node.start_byte:name_node.end_byte].decode("utf-8")
            qualified = scope + "." + name if scope else name
            start = node.start_point.row + 1
            end = node.end_point.row + (1 if node.end_point.column else 0)
            if suffix == ".py" and node.parent and node.parent.type == "decorated_definition":
                start = node.parent.start_point.row + 1
            signature = redact(source_lines[start - 1])[:250]
            symbols.append({"name": name, "qualified": qualified, "kind": node.type,
                            "start": start, "end": max(start, end), "signature": signature})
            next_scope = qualified
            references.setdefault(qualified, set())
        if node.type == "identifier" and scope in references:
            references[scope].add(source[node.start_byte:node.end_byte].decode("utf-8"))
        if node.type == "import_statement" and suffix != ".py":
            imported = node.child_by_field_name("source")
            if imported:
                imports.append(source[imported.start_byte:imported.end_byte].decode().strip("\"'"))
                import_ranges.append({"start": node.start_point.row + 1,
                                      "end": node.end_point.row + (1 if node.end_point.column else 0)})
        stack.extend((child, next_scope) for child in reversed(node.named_children))
    if suffix == ".py":
        try:
            python_tree = ast.parse(raw)
            for node in ast.walk(python_tree):
                if isinstance(node, ast.ImportFrom):
                    imports.append("." * node.level + (node.module or ""))
                    import_ranges.append({"start": node.lineno, "end": node.end_lineno})
                elif isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                    import_ranges.append({"start": node.lineno, "end": node.end_lineno})
        except SyntaxError:
            pass
    for symbol in symbols:
        symbol["references"] = sorted(references.get(symbol["qualified"], set()) - {symbol["name"]})[:100]
    return {"language": {".py": "python", ".ts": "typescript", ".tsx": "tsx", ".js": "javascript", ".jsx": "jsx"}[suffix],
            "parsed": True, "syntax_errors": tree.root_node.has_error,
            "parse_limited": visited > 100000 or len(symbols) > 1000 or len(imports) > 200,
            "symbols": symbols[:1000], "imports": sorted({redact(x) for x in imports})[:200], "import_ranges": import_ranges[:200]}


class CodeIndex:
    def __init__(self, guard: Engine, policy: RuntimePolicy | None = None):
        self.guard = guard
        self.policy = policy or RuntimePolicy()
        self._last_report = None
        self._last_monotonic = 0.0
        self.files_limited = False
        with guard.connect() as con:
            con.execute("CREATE TABLE IF NOT EXISTS code_index(path TEXT PRIMARY KEY, sha TEXT, bytes INTEGER, metadata TEXT, counts TEXT)")
            con.execute("CREATE TABLE IF NOT EXISTS index_meta(key TEXT PRIMARY KEY, value TEXT)")
            version = con.execute("SELECT value FROM index_meta WHERE key='schema_version'").fetchone()
            if not version or version[0] != "2":
                con.execute("DELETE FROM code_index")
                con.execute("INSERT OR REPLACE INTO index_meta VALUES('schema_version','2')")

    def update_file(self, path: str, con=None):
        _, raw, sha, size = self.guard.load(path)
        if size > self.policy.index_limits["file_bytes"]:
            raise GuardError("source exceeds hardware profile file limit; use smaller files or standard hardware profile")
        if con is not None:
            row = con.execute("SELECT sha,metadata FROM code_index WHERE path=?", (path,)).fetchone()
        else:
            with self.guard.connect() as c:
                row = c.execute("SELECT sha,metadata FROM code_index WHERE path=?", (path,)).fetchone()
        if row and row[0] == sha:
            return json.loads(row[1]), sha, raw, False
        meta = outline(path, raw)
        counts = dict(Counter(terms(redact(raw) + " " + path)).most_common(1000))
        if con is not None:
            if not row and con.execute("SELECT count(*) FROM code_index").fetchone()[0] >= 5000:
                raise GuardError("code index capacity reached (5000 files)")
            con.execute("INSERT OR REPLACE INTO code_index VALUES(?,?,?,?,?)", (path, sha, size, encode(meta), encode(counts)))
        else:
            with self.guard.connect() as c:
                if not row and c.execute("SELECT count(*) FROM code_index").fetchone()[0] >= 5000:
                    raise GuardError("code index capacity reached (5000 files)")
                c.execute("INSERT OR REPLACE INTO code_index VALUES(?,?,?,?,?)", (path, sha, size, encode(meta), encode(counts)))
        return meta, sha, raw, True

    def refresh(self, max_files: int = 250) -> dict:
        limits = self.policy.index_limits
        max_files = min(max_files, limits["max_files"])
        started, seen, parsed, unchanged = time.monotonic(), set(), 0, 0
        candidates = sorted(self.guard.walk(max_entries=limits["scan_entries"], seconds=limits["scan_seconds"]))
        scan_limited = self.guard.scan_limited
        with self.guard.connect() as con:
            row = con.execute("SELECT value FROM index_meta WHERE key='cursor'").fetchone()
            cursor = row[0] if row else ""
            # Rotate bounded batches so later files are not permanently starved.
            ordered = [x for x in candidates if x[0] > cursor] + [x for x in candidates if x[0] <= cursor]
            processed, skipped, source_bytes, limited = 0, 0, 0, scan_limited
            for path, size in ordered:
                if (processed >= max_files or parsed >= limits["max_reparsed"]
                        or time.monotonic() - started > limits["seconds"]
                        or source_bytes + size > limits["source_bytes"]):
                    limited = True
                    break
                processed += 1
                cursor = path
                seen.add(path)
                if size > limits["file_bytes"]:
                    skipped += 1
                    continue
                try:
                    _, _, _, changed = self.update_file(path, con=con)
                except (GuardError, OSError):
                    skipped += 1
                    continue
                source_bytes += size
                parsed += int(changed)
                unchanged += int(not changed)
            limited |= bool(skipped)
            removed = 0
            if not scan_limited and processed == len(candidates):
                for (path,) in con.execute("SELECT path FROM code_index").fetchall():
                    if path not in seen:
                        con.execute("DELETE FROM code_index WHERE path=?", (path,))
                        removed += 1
            con.execute("INSERT OR REPLACE INTO index_meta VALUES('last_refresh',?)", (str(time.time()),))
            con.execute("INSERT OR REPLACE INTO index_meta VALUES('limited',?)", (str(limited),))
            con.execute("INSERT OR REPLACE INTO index_meta VALUES('cursor',?)", (cursor,))
            total = con.execute("SELECT count(*) FROM code_index").fetchone()[0]
        limited |= total > limits["inventory_records"]
        report = {"indexed": total, "visited_files": processed, "reparsed": parsed, "unchanged": unchanged,
                  "removed": removed, "skipped": skipped, "limited": limited, "cached": False,
                  "source_bytes_read": source_bytes, "duration_ms": round((time.monotonic() - started) * 1000, 2),
                  "hardware": self.policy.hardware, "method": "content SHA-256 + Tree-sitter + lexical term counts"}
        self._last_report, self._last_monotonic = report, time.monotonic()
        return report

    def ensure(self):
        age = time.monotonic() - self._last_monotonic
        if self._last_report is not None and age < self.policy.index_limits["refresh_ttl"]:
            return {**self._last_report, "cached": True, "age_seconds": round(age, 3)}
        return self.refresh()

    @staticmethod
    def import_candidates(path, target):
        if path.endswith(".py"):
            if target.startswith("."):
                level = len(target) - len(target.lstrip("."))
                base = PurePosixPath(path).parent
                for _ in range(level - 1):
                    base = base.parent
                base = str(base / target[level:].replace(".", "/"))
            else:
                base = target.replace(".", "/")
            return [base + ".py", base + "/__init__.py"]
        if target.startswith("."):
            base = posixpath.normpath(str(PurePosixPath(path).parent / target))
            return [base] + [base + ext for ext in (".ts", ".tsx", ".js", ".jsx", ".json")] + [base + "/index" + ext for ext in (".ts", ".tsx", ".js", ".jsx")]
        return []

    def refresh_dependencies(self, paths):
        files, resolved, attempted = self.files(required=paths), [], set()
        for path in paths:
            for target in files.get(path, {}).get("metadata", {}).get("imports", [])[:24]:
                for candidate in self.import_candidates(path, target):
                    if candidate in attempted:
                        break
                    if len(attempted) >= 128 or len(resolved) >= 24:
                        return resolved
                    attempted.add(candidate)
                    try:
                        canonical = self.guard.path(candidate).relative_to(self.guard.root).as_posix()
                        self.update_file(canonical)
                        resolved.append(canonical)
                        break
                    except (GuardError, OSError):
                        continue
        return resolved

    def files(self, required=None) -> dict:
        with self.guard.connect() as con:
            cap = self.policy.index_limits["inventory_records"]
            rows = con.execute("SELECT path,sha,bytes,metadata,counts FROM code_index ORDER BY rowid DESC LIMIT ?", (cap,)).fetchall()
            self.files_limited = con.execute("SELECT count(*) FROM code_index").fetchone()[0] > len(rows)
            present = {row[0] for row in rows}
            for path in list(dict.fromkeys(required or []))[:48]:
                if path not in present:
                    row = con.execute("SELECT path,sha,bytes,metadata,counts FROM code_index WHERE path=?", (path,)).fetchone()
                    if row:
                        rows.append(row)
        return {r[0]: {"sha256": r[1], "bytes": r[2], "metadata": json.loads(r[3]), "counts": json.loads(r[4])} for r in rows}

    def rank(self, task: str, files: dict) -> list[tuple[str, float]]:
        wanted = set(terms(task))
        lengths = {p: sum(v["counts"].values()) for p, v in files.items()}
        average = sum(lengths.values()) / max(len(files), 1) or 1
        frequencies = {t: sum(t in v["counts"] for v in files.values()) for t in wanted}
        result = []
        for path, record in files.items():
            score = 0.0
            for term in wanted:
                freq = record["counts"].get(term, 0)
                if freq:
                    idf = math.log(1 + (len(files) - frequencies[term] + .5) / (frequencies[term] + .5))
                    score += idf * freq * 2.2 / (freq + 1.2 * (.25 + .75 * lengths[path] / average))
                if term in terms(path):
                    score += 3
                if any(term in terms(s["qualified"]) for s in record["metadata"]["symbols"]):
                    score += 2
            if score > 0:
                result.append((path, score))
        return sorted(result, key=lambda x: (-x[1], x[0]))

    def edges(self, files: dict) -> tuple[dict, dict]:
        edges, unresolved = {}, {}
        for path, record in files.items():
            neighbors, external = [], []
            for target in record["metadata"]["imports"]:
                candidates = self.import_candidates(path, target)
                resolved = next((c for c in candidates if c in files), None)
                if resolved:
                    neighbors.append(resolved)
                else:
                    external.append(target)
            edges[path], unresolved[path] = sorted(set(neighbors)), sorted(set(external))
        return edges, unresolved

    def snippet(self, path: str, symbol: str = "", start: int = 1, count: int = 80) -> dict:
        meta, sha, raw, _ = self.update_file(path)
        lines = redact(raw).splitlines()
        end = min(start + count - 1, len(lines))
        method = "line_window"
        if symbol:
            candidates = [s for s in meta["symbols"] if symbol in (s["name"], s["qualified"])]
            if len(candidates) != 1:
                return {"path": path, "found": bool(candidates), "ambiguous": len(candidates) > 1, "candidates": candidates[:20]}
            item = candidates[0]
            start, end, method = item["start"], min(item["end"], item["start"] + count - 1), "tree_sitter_symbol"
        result = {"path": path, "sha256": sha, "start": start, "end": end, "method": method,
                  "syntax_errors": meta["syntax_errors"], "text": "\n".join(lines[start - 1:end]),
                  "truncated": bool(symbol and item["end"] > end), "next_line": end + 1, "content_is_untrusted": True}
        return result
