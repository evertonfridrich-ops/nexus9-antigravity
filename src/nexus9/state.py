"""Revisioned local memory, snapshots, validated answer cache and session ledgers."""
from __future__ import annotations

import difflib
import json
import time

from .guard import Engine, GuardError, encode, redact


def clean(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    return value


class State:
    def __init__(self, guard: Engine):
        self.guard = guard
        with guard.connect() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS memories(name TEXT PRIMARY KEY, revision INTEGER, body TEXT, hashes TEXT);
            CREATE TABLE IF NOT EXISTS sessions(name TEXT PRIMARY KEY, profile TEXT, call_budget INTEGER, total_budget INTEGER, used INTEGER, closed INTEGER);
            CREATE TABLE IF NOT EXISTS snapshots(session TEXT, path TEXT, revision INTEGER, sha TEXT, text TEXT, at REAL, PRIMARY KEY(session,path,revision));
            CREATE TABLE IF NOT EXISTS answers(key TEXT PRIMARY KEY, answer TEXT, dependencies TEXT, expires REAL);
            CREATE TABLE IF NOT EXISTS usage(request_id TEXT PRIMARY KEY, body TEXT, at REAL);
            CREATE TABLE IF NOT EXISTS nexus_events(id INTEGER PRIMARY KEY, at REAL, operation TEXT, bytes INTEGER, duration_ms REAL, session TEXT, status TEXT);
            """)

    def open(self, name, profile, call_budget_bytes, total_budget_bytes):
        with self.guard.connect() as con:
            row = con.execute("SELECT profile,call_budget,total_budget,used,closed FROM sessions WHERE name=?", (name,)).fetchone()
            if row:
                if row[:3] != (profile, call_budget_bytes, total_budget_bytes) or row[4]:
                    raise GuardError("session already exists with different settings or is closed; use a new name")
                return {"session": name, "used_bytes": row[3], "existing": True}
            if con.execute("SELECT count(*) FROM sessions").fetchone()[0] >= 100:
                raise GuardError("session capacity reached (100)")
            con.execute("INSERT INTO sessions VALUES(?,?,?,?,0,0)", (name, profile, call_budget_bytes, total_budget_bytes))
        return {"session": name, "used_bytes": 0, "opened": True}

    def session(self, name):
        if not name:
            return {"call_budget": 24576, "profile": "balanced"}
        with self.guard.connect() as con:
            row = con.execute("SELECT profile,call_budget,total_budget,used,closed FROM sessions WHERE name=?", (name,)).fetchone()
        if not row or row[4]:
            raise GuardError("session unavailable or closed")
        return {"profile": row[0], "call_budget": row[1], "total_budget": row[2], "used": row[3]}

    def close(self, name):
        with self.guard.connect() as con:
            con.execute("UPDATE sessions SET closed=1 WHERE name=?", (name,))
        return {"session": name, "closed": True}

    def record(self, operation, result, started, session=None, status="ok", charge=True):
        size = len(encode(result).encode())
        with self.guard.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if session and charge:
                row = con.execute("SELECT call_budget,total_budget,used,closed FROM sessions WHERE name=?", (session,)).fetchone()
                if not row or row[3]:
                    raise GuardError("session unavailable or closed")
                if size > row[0] or row[2] + size > row[1]:
                    raise GuardError("local response budget exhausted; reduce the payload or explicitly open a new session")
                con.execute("UPDATE sessions SET used=used+? WHERE name=?", (size, session))
            con.execute("INSERT INTO nexus_events(at,operation,bytes,duration_ms,session,status) VALUES(?,?,?,?,?,?)",
                        (time.time(), operation, size, (time.monotonic() - started) * 1000, session, status))
            con.execute("DELETE FROM nexus_events WHERE id NOT IN (SELECT id FROM nexus_events ORDER BY id DESC LIMIT 10000)")

    def memory_save(self, name, expected_revision, body):
        if len(encode(body).encode()) > 24000:
            raise GuardError("memory exceeds 24 KiB")
        hashes = {}
        for path in body["files"]:
            try:
                _, _, sha, _ = self.guard.load(path)
                hashes[path] = sha
            except (GuardError, OSError):
                # Missing future files are explicit; never store a made-up digest.
                hashes[path] = None
        with self.guard.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT revision FROM memories WHERE name=?", (name,)).fetchone()
            revision = row[0] if row else 0
            if revision != expected_revision:
                raise GuardError(f"memory revision conflict; current revision is {revision}")
            if not row and con.execute("SELECT count(*) FROM memories").fetchone()[0] >= 100:
                raise GuardError("memory capacity reached (100)")
            con.execute("INSERT OR REPLACE INTO memories VALUES(?,?,?,?)", (name, revision + 1, encode(clean(body)), encode(hashes)))
        return {"name": name, "revision": revision + 1, "saved": True, "host_history_replaced": False}

    def memory(self, name, resume=False):
        with self.guard.connect() as con:
            row = con.execute("SELECT revision,body,hashes FROM memories WHERE name=?", (name,)).fetchone()
        if not row:
            return {"name": name, "found": False}
        result = {"name": name, "found": True, "revision": row[0], "body": json.loads(row[1]), "content_is_untrusted": True,
                  "provenance": "facts and verification labels supplied by caller; file fingerprints observed locally"}
        if resume:
            statuses = []
            for path, old in json.loads(row[2]).items():
                try:
                    _, _, current, _ = self.guard.load(path)
                    status = "unchanged" if current == old else "changed" if old else "new_since_save"
                except (GuardError, OSError):
                    current, status = None, "missing_or_denied"
                statuses.append({"path": path, "status": status, "sha256": current})
            result.update(files=statuses, revalidation_required=any(x["status"] != "unchanged" for x in statuses))
        return result

    def remember(self, session, path, expected_revision):
        if not session:
            raise GuardError("remember_read requires an explicit session")
        self.session(session)
        _, raw, sha, _ = self.guard.load(path)
        text = redact(raw)
        if len(text.encode()) > 131072:
            raise GuardError("snapshot exceeds 128 KiB; use symbol packets instead")
        with self.guard.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            revision = con.execute("SELECT coalesce(max(revision),0) FROM snapshots WHERE session=? AND path=?", (session, path)).fetchone()[0]
            if revision != expected_revision:
                raise GuardError(f"snapshot revision conflict; current revision is {revision}")
            con.execute("INSERT INTO snapshots VALUES(?,?,?,?,?,?)", (session, path, revision + 1, sha, text, time.time()))
            con.execute("DELETE FROM snapshots WHERE rowid NOT IN (SELECT rowid FROM snapshots ORDER BY at DESC LIMIT 100)")
        return {"path": path, "sha256": sha, "revision": revision + 1, "remembered": True,
                "note": "Snapshot explicitly acknowledged by caller; not proof content remains in host context."}

    def delta(self, session, path, base_revision=None):
        if not session:
            raise GuardError("delta requires an explicit session")
        _, raw, sha, _ = self.guard.load(path)
        with self.guard.connect() as con:
            if base_revision:
                row = con.execute("SELECT revision,sha,text FROM snapshots WHERE session=? AND path=? AND revision=?", (session, path, base_revision)).fetchone()
            else:
                row = con.execute("SELECT revision,sha,text FROM snapshots WHERE session=? AND path=? ORDER BY revision DESC LIMIT 1", (session, path)).fetchone()
        if not row:
            return {"path": path, "baseline_available": False, "action": "read current source, then explicitly remember_read"}
        if sha == row[1]:
            return {"path": path, "base_revision": row[0], "unchanged": True, "sha256": sha,
                    "note": "Reuse only if the baseline remains in your active context."}
        diff = list(difflib.unified_diff(row[2].splitlines(), redact(raw).splitlines(), fromfile=path + "@baseline", tofile=path + "@current", lineterm="", n=3))
        return {"path": path, "base_revision": row[0], "unchanged": False, "sha256": sha, "diff": diff,
                "baseline_advanced": False, "content_is_untrusted": True}

    def cache_save(self, key, answer, files, ttl_seconds):
        dependencies = {p: self.guard.load(p)[2] for p in files}
        with self.guard.connect() as con:
            con.execute("INSERT OR REPLACE INTO answers VALUES(?,?,?,?)", (key, redact(answer), encode(dependencies), time.time() + ttl_seconds))
            con.execute("DELETE FROM answers WHERE key NOT IN (SELECT key FROM answers ORDER BY expires DESC LIMIT 100)")
        return {"key": key, "saved": True, "dependencies": dependencies}

    def cache(self, key):
        with self.guard.connect() as con:
            row = con.execute("SELECT answer,dependencies,expires FROM answers WHERE key=?", (key,)).fetchone()
        if not row or row[2] < time.time():
            return {"key": key, "hit": False, "reason": "missing_or_expired"}
        for path, digest in json.loads(row[1]).items():
            try:
                current = self.guard.load(path)[2]
            except (GuardError, OSError):
                current = None
            if current != digest:
                return {"key": key, "hit": False, "reason": "source_changed", "path": path}
        return {"key": key, "hit": True, "answer": row[0], "source_validated": True, "content_is_untrusted": True,
                "note": "Exact-key cache; no claim of zero generation tokens or semantic equivalence."}

    def usage_record(self, body):
        if body["cached_input_tokens"] > body["input_tokens"]:
            raise GuardError("cached input tokens cannot exceed total input tokens")
        text = encode(clean(body))
        with self.guard.connect() as con:
            existing = con.execute("SELECT body FROM usage WHERE request_id=?", (body["request_id"],)).fetchone()
            if existing:
                if existing[0] != text:
                    raise GuardError("request_id already recorded with different usage")
                return {"recorded": False, "duplicate": True}
            if con.execute("SELECT count(*) FROM usage").fetchone()[0] >= 10000:
                raise GuardError("usage ledger capacity reached (10000)")
            con.execute("INSERT INTO usage VALUES(?,?,?)", (body["request_id"], text, time.time()))
        return {"recorded": True, "source": body["source"], "automatically_observed": False}

    def metrics(self):
        with self.guard.connect() as con:
            events = con.execute("SELECT operation,count(*),sum(bytes),round(avg(duration_ms),2) FROM nexus_events GROUP BY operation").fetchall()
            sessions = con.execute("SELECT name,used,total_budget,closed FROM sessions ORDER BY name").fetchall()
            usage = [json.loads(r[0]) for r in con.execute("SELECT body FROM usage")]
        return {"local_events": [{"operation": r[0], "calls": r[1], "result_bytes": r[2], "mean_ms": r[3]} for r in events],
                "sessions": [{"name": r[0], "used_bytes": r[1], "budget_bytes": r[2], "closed": bool(r[3])} for r in sessions],
                "reported_usage": {"requests": len(usage), "input_tokens": sum(r["input_tokens"] for r in usage),
                                   "output_tokens": sum(r["output_tokens"] for r in usage),
                                   "cached_input_tokens": sum(r["cached_input_tokens"] for r in usage),
                                   "source": "caller-supplied; not independently observed"},
                "automatic_provider_tokens": None, "actual_cost": None,
                "note": "Local output byte limits do not impose model token limits or erase existing context."}
