"""Revisioned investigations with immutable evidence and derived freshness.

The labels supports/refutes are assessments supplied by the caller. File hashes
and optional process receipts are local observations, not semantic verification.
Reads derive status without mutating history or silently refreshing proof.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
import time

from pydantic import ValidationError

from .guard import GuardError, encode
from .investigation_models import InvestigationBody, InvestigationGet, InvestigationSave, RegressionCases
from .state import clean

COLLECTIONS = ("hypotheses", "notes", "evidence", "conclusions", "criteria", "regressions")
MAX_BODY = 32768
MAX_OUTPUT = 20000
MAX_NODES = 100
MAX_REVISIONS = 500
SHA = re.compile(r"^[0-9a-f]{64}$")


def _validate(model, value):
    try:
        return model.model_validate(value)
    except ValidationError:
        raise GuardError("invalid investigation parameters; discover the operation schema") from None


class InvestigationStore:
    def __init__(self, guard, runner=None):
        self.guard = guard
        self.runner = runner
        with guard.connect() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS investigations(
                name TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                body TEXT NOT NULL, snapshots TEXT NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS investigation_revisions(
                name TEXT NOT NULL, revision INTEGER NOT NULL, body TEXT NOT NULL,
                snapshots TEXT NOT NULL, updated REAL NOT NULL,
                PRIMARY KEY(name,revision));
            """)

    def _read(self, name):
        with self.guard.connect() as con:
            row = con.execute("SELECT revision,body,snapshots FROM investigations WHERE name=?", (name,)).fetchone()
        if row is None:
            return None
        return row[0], json.loads(row[1]), json.loads(row[2])

    @staticmethod
    def _merge(old, incoming, domain_supplied):
        if old is None:
            return incoming, [], [node["id"] for key in COLLECTIONS for node in incoming[key]]
        if incoming["objective"] != old["objective"]:
            raise GuardError("investigation objective is immutable; create a new investigation")
        if domain_supplied and incoming["domain"] != old["domain"]:
            raise GuardError("investigation domain is immutable")
        merged = deepcopy(old)
        revised, added = [], []
        for key in COLLECTIONS:
            by_id = {node["id"]: node for node in merged[key]}
            seen = set()
            for node in incoming[key]:
                identifier = node["id"]
                if identifier in seen:
                    raise GuardError("duplicate node identity in investigation update")
                seen.add(identifier)
                if identifier not in by_id:
                    merged[key].append(node)
                    by_id[identifier] = node
                    added.append(identifier)
                elif by_id[identifier] != node:
                    mutable = "evidence_ids" if key == "conclusions" else "conclusion_ids" if key == "criteria" else None
                    if not mutable or {k: v for k, v in by_id[identifier].items() if k != mutable} != {
                        k: v for k, v in node.items() if k != mutable
                    }:
                        raise GuardError("existing investigation nodes are immutable except revisioned proof links")
                    by_id[identifier][mutable] = node[mutable]
                    revised.append(identifier)
        return merged, revised, added

    @staticmethod
    def _references(body):
        count = sum(len(body[key]) for key in COLLECTIONS)
        if count > MAX_NODES or len(encode(body).encode()) > MAX_BODY:
            raise GuardError("investigation exceeds 100 nodes or 32 KiB")
        identities = [node["id"] for key in COLLECTIONS for node in body[key]]
        if len(set(identities)) != len(identities):
            raise GuardError("investigation node identities must be globally unique")
        maps = {key: {node["id"]: node for node in body[key]} for key in COLLECTIONS}
        for evidence in body["evidence"]:
            if len(set(evidence["files"])) != len(evidence["files"]):
                raise GuardError("duplicate evidence source")
            if len(set(evidence["hypothesis_ids"])) != len(evidence["hypothesis_ids"]) or any(
                ref not in maps["hypotheses"] for ref in evidence["hypothesis_ids"]
            ):
                raise GuardError("evidence must reference unique existing hypotheses")
        for conclusion in body["conclusions"]:
            for key, collection in (("evidence_ids", "evidence"), ("hypothesis_ids", "hypotheses")):
                if len(set(conclusion[key])) != len(conclusion[key]) or any(ref not in maps[collection] for ref in conclusion[key]):
                    raise GuardError("conclusion contains duplicate or unknown references")
            covered = {ref for evidence_id in conclusion["evidence_ids"] for ref in maps["evidence"][evidence_id]["hypothesis_ids"]}
            if not set(conclusion["hypothesis_ids"]).issubset(covered):
                raise GuardError("conclusion proof must cover each referenced hypothesis")
        for criterion in body["criteria"]:
            if len(set(criterion["conclusion_ids"])) != len(criterion["conclusion_ids"]) or any(
                ref not in maps["conclusions"] for ref in criterion["conclusion_ids"]
            ):
                raise GuardError("criterion must reference unique existing conclusions")
        for case in body["regressions"]:
            if case["note_id"] not in maps["notes"] or case["hypothesis_id"] not in maps["hypotheses"]:
                raise GuardError("regression case must link an existing note and hypothesis")
        return maps

    def _run(self, run_id):
        if self.runner is None:
            raise GuardError("observed test runner unavailable")
        result = self.runner.get_run(run_id)
        if not isinstance(result, dict) or result.get("provenance") != "nexus9_observed_process":
            raise GuardError("test run is not a NEXUS9 observed process receipt")
        hashes = result.get("source_hashes")
        receipt = result.get("receipt_sha256")
        if not isinstance(hashes, dict) or not isinstance(receipt, str) or SHA.fullmatch(receipt) is None:
            raise GuardError("test run receipt is unavailable or invalid")
        if any(not isinstance(path, str) or not isinstance(sha, str) or SHA.fullmatch(sha) is None for path, sha in hashes.items()):
            raise GuardError("test run source fingerprints are invalid")
        return result

    def _capture(self, evidence, cache):
        run = self._run(evidence["run_id"]) if evidence["run_id"] else None
        hashes = {}
        for source in evidence["files"]:
            path = self.guard.path(source).relative_to(self.guard.root).as_posix()
            if path in hashes:
                raise GuardError("duplicate canonical evidence source")
            if run is not None:
                if path not in run["source_hashes"]:
                    raise GuardError("evidence source is not covered by the observed test receipt")
                hashes[path] = run["source_hashes"][path]
            else:
                if path not in cache:
                    _, _, sha, size = self.guard.load(path)
                    cache[path] = sha, size
                    if sum(value[1] for value in cache.values()) > 8 * 1024 * 1024:
                        raise GuardError("investigation source snapshot exceeds 8 MiB")
                hashes[path] = cache[path][0]
        return {"files": hashes, "run_id": evidence["run_id"],
                "run_receipt_sha256": run["receipt_sha256"] if run is not None else None}

    def save(self, name, expected_revision, body):
        request = _validate(InvestigationSave, {"name": name, "expected_revision": expected_revision, "body": body})
        incoming = clean(request.body.model_dump())
        with self.guard.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT revision,body,snapshots FROM investigations WHERE name=?", (name,)).fetchone()
            revision = row[0] if row else 0
            if revision != expected_revision:
                raise GuardError(f"investigation revision conflict; current revision is {revision}")
            if not row and con.execute("SELECT count(*) FROM investigations").fetchone()[0] >= 100:
                raise GuardError("investigation capacity reached (100)")
            if con.execute("SELECT count(*) FROM investigation_revisions").fetchone()[0] >= MAX_REVISIONS:
                raise GuardError("investigation history capacity reached (500 revisions total)")
            old = json.loads(row[1]) if row else None
            snapshots = json.loads(row[2]) if row else {}
            merged, revised, added = self._merge(old, incoming, "domain" in request.body.model_fields_set)
            merged = _validate(InvestigationBody, merged).model_dump()
            self._references(merged)
            cache = {}
            for evidence in merged["evidence"]:
                if evidence["id"] not in snapshots:
                    snapshots[evidence["id"]] = self._capture(evidence, cache)
            sources = {path for snapshot in snapshots.values() for path in snapshot["files"]}
            if len(sources) > 30:
                raise GuardError("investigation source capacity reached (30 unique paths)")
            payload, observed = encode(merged), encode(snapshots)
            if len(observed.encode()) > 65536:
                raise GuardError("investigation snapshot metadata exceeds 64 KiB")
            now = time.time()
            con.execute("INSERT OR REPLACE INTO investigations VALUES(?,?,?,?,?)", (name, revision + 1, payload, observed, now))
            con.execute("INSERT INTO investigation_revisions VALUES(?,?,?,?,?)", (name, revision + 1, payload, observed, now))
        return {"name": name, "revision": revision + 1, "saved": True, "added_ids": added,
                "revised_proof_links": revised, "evidence_snapshots_refreshed": False,
                "body_sha256": hashlib.sha256(payload.encode()).hexdigest(), "writes_project_code": False}

    def _derive(self, body, snapshots):
        evidence_status, current_files, run_cache = {}, {}, {}
        for evidence in body["evidence"]:
            snapshot = snapshots[evidence["id"]]
            files = []
            for path, expected in snapshot["files"].items():
                if path not in current_files:
                    try:
                        current_files[path] = self.guard.load(path)[2]
                    except (GuardError, OSError):
                        current_files[path] = None
                current = current_files[path]
                files.append({"path": path, "sha256": expected,
                              "status": "unchanged" if current == expected else "missing_or_denied" if current is None else "changed"})
            run_summary = None
            stale = any(item["status"] != "unchanged" for item in files)
            if snapshot["run_id"]:
                run_id = snapshot["run_id"]
                if run_id not in run_cache:
                    try:
                        run_cache[run_id] = self._run(run_id)
                    except (GuardError, OSError):
                        run_cache[run_id] = None
                run = run_cache[run_id]
                run_current = bool(run and run.get("fresh") is True and run.get("receipt_sha256") == snapshot["run_receipt_sha256"])
                stale = stale or not run_current
                run_summary = {"run_id": run_id, "current": run_current,
                               "passed": bool(run and run.get("passed") is True),
                               "exit_code": run.get("exit_code") if run else None,
                               "provenance": "nexus9_observed_process" if run else "unavailable"}
            state = "needs_revalidation" if stale else "current" if files or snapshot["run_id"] else "reported_only"
            evidence_status[evidence["id"]] = {"status": state, "sources": files, "test_run": run_summary,
                "assessment_origin": "caller_supplied", "content_is_untrusted": True}
        hypotheses = {}
        for hypothesis in body["hypotheses"]:
            linked = [e for e in body["evidence"] if hypothesis["id"] in e["hypothesis_ids"]]
            labels = {e["result"] for e in linked if evidence_status[e["id"]]["status"] == "current"}
            state = ("contested" if {"supports", "refutes"}.issubset(labels) else "refuted" if "refutes" in labels else
                     "supported_by_current_evidence" if "supports" in labels else
                     "needs_revalidation" if any(evidence_status[e["id"]]["status"] == "needs_revalidation" for e in linked) else "open")
            hypotheses[hypothesis["id"]] = {"status": state, "evidence_ids": [e["id"] for e in linked]}
        conclusions = {}
        for conclusion in body["conclusions"]:
            states = [evidence_status[ref]["status"] for ref in conclusion["evidence_ids"]]
            hstates = [hypotheses[ref]["status"] for ref in conclusion["hypothesis_ids"]]
            selected_support = all(any(
                item["id"] in conclusion["evidence_ids"] and hypothesis_id in item["hypothesis_ids"] and
                item["result"] == "supports" and evidence_status[item["id"]]["status"] == "current"
                for item in body["evidence"]
            ) for hypothesis_id in conclusion["hypothesis_ids"])
            state = ("contested" if "contested" in hstates else "refuted" if "refuted" in hstates else
                     "needs_revalidation" if "needs_revalidation" in states or "needs_revalidation" in hstates else
                     "supported_by_current_evidence" if selected_support and all(s == "current" for s in states) and all(
                         s == "supported_by_current_evidence" for s in hstates) else "open")
            conclusions[conclusion["id"]] = {"status": state, "evidence_ids": conclusion["evidence_ids"],
                "hypothesis_ids": conclusion["hypothesis_ids"]}
        criteria = {}
        for criterion in body["criteria"]:
            linked = [conclusions[ref] for ref in criterion["conclusion_ids"]]
            states = [item["status"] for item in linked]
            tests_ok = all(any(evidence_status[ref]["test_run"] and evidence_status[ref]["test_run"]["current"] and
                              evidence_status[ref]["test_run"]["passed"] for ref in item["evidence_ids"]) for item in linked)
            state = ("contested" if "contested" in states else "not_met" if "refuted" in states else
                     "needs_revalidation" if "needs_revalidation" in states else
                     "supported_by_current_evidence" if all(s == "supported_by_current_evidence" for s in states) and
                     (not criterion["requires_observed_test"] or tests_ok) else "open")
            criteria[criterion["id"]] = {"status": state, "requires_observed_test": criterion["requires_observed_test"],
                "conclusion_ids": criterion["conclusion_ids"], "observed_passing_tests": tests_ok}
        states = [item["status"] for item in criteria.values()]
        overall = ("contested" if "contested" in states else "needs_revalidation" if "needs_revalidation" in states else
                   "supported_by_current_evidence" if states and all(s == "supported_by_current_evidence" for s in states) else "open")
        return evidence_status, hypotheses, conclusions, criteria, overall

    def get(self, name, conclusion_id="", offset=0, limit=5):
        _validate(InvestigationGet, {"name": name, "conclusion_id": conclusion_id, "offset": offset, "limit": limit})
        stored = self._read(name)
        if stored is None:
            return {"name": name, "found": False}
        revision, body, snapshots = stored
        evidence, hypotheses, conclusions, criteria, overall = self._derive(body, snapshots)
        focus = None
        if conclusion_id:
            if conclusion_id not in conclusions:
                raise GuardError("conclusion not found in investigation")
            selected = conclusions[conclusion_id]
            focus = {conclusion_id, *selected["hypothesis_ids"], *selected["evidence_ids"]}
            for ref in selected["hypothesis_ids"]:
                focus.update(hypotheses[ref]["evidence_ids"])
        statuses = {**evidence, **hypotheses, **conclusions, **criteria}
        nodes = []
        for kind in COLLECTIONS:
            for node in body[kind]:
                if focus is not None and node["id"] not in focus:
                    continue
                nodes.append({"kind": kind, **node, **statuses.get(node["id"], {"status": "registered"})})
        details = nodes[offset:offset + limit]
        acceptance_ids = {ref for criterion in body["criteria"] for ref in criterion["conclusion_ids"]}
        relevant_conclusions = ([conclusions[conclusion_id]] if conclusion_id else
                                [conclusions[ref] for ref in sorted(acceptance_ids)] if acceptance_ids else list(conclusions.values()))
        active = {ref for conclusion in relevant_conclusions for ref in conclusion["evidence_ids"]}
        for conclusion in relevant_conclusions:
            if conclusion["status"] == "needs_revalidation":
                for ref in conclusion["hypothesis_ids"]:
                    if hypotheses[ref]["status"] == "needs_revalidation":
                        active.update(hypotheses[ref]["evidence_ids"])
        next_checks = [{"evidence_id": ref, "reason": evidence[ref]["status"],
                        "action": "collect new evidence and revise proof links; do not refresh old fingerprints"}
                       for ref in sorted(active) if evidence[ref]["status"] != "current"]
        relevant_hypotheses = {ref for conclusion in relevant_conclusions for ref in conclusion["hypothesis_ids"]}
        for ref in sorted(relevant_hypotheses):
            if hypotheses[ref]["status"] in {"contested", "refuted"}:
                next_checks.append({"hypothesis_id": ref, "reason": hypotheses[ref]["status"],
                    "evidence_ids": hypotheses[ref]["evidence_ids"],
                    "action": "investigate competing evidence and execute a discriminating check; do not hide the opposing result"})
        if any(item["status"] == "open" for item in relevant_conclusions):
            next_checks.append({"reason": "supporting_evidence_required", "action": "link current supporting evidence for each referenced hypothesis"})
        relevant_criteria = [item for item in criteria.values() if not conclusion_id or conclusion_id in item["conclusion_ids"]]
        if any(item["requires_observed_test"] and not item["observed_passing_tests"] for item in relevant_criteria):
            next_checks.append({"reason": "observed_passing_test_required", "action": "run an explicitly enabled check profile; caller labels are insufficient"})
        result = {"name": name, "found": True, "revision": revision, "objective": body["objective"], "domain": body["domain"],
            "status": conclusions[conclusion_id]["status"] if conclusion_id else overall,
            "conclusion_id": conclusion_id or None,
            "hypotheses": [{"id": key, "status": value["status"]} for key, value in hypotheses.items()],
            "conclusions": [{"id": key, "status": value["status"]} for key, value in conclusions.items()],
            "criteria": [{"id": key, **value} for key, value in criteria.items()],
            "nodes": details, "offset": offset, "total_nodes": len(nodes),
            "next_offset": offset + len(details) if offset + len(details) < len(nodes) else None,
            "next_checks": next_checks, "revalidation_required": any(evidence[ref]["status"] == "needs_revalidation" for ref in active),
            "content_is_untrusted": True,
            "scope": "Supports/refutes and semantic coverage are caller assessments. Source freshness and process receipts are local observations; this is not proof of correctness or host model compliance.",
            "revision_history_preserved": True}
        while len(encode(result).encode()) > MAX_OUTPUT and len(result["nodes"]) > 1:
            result["nodes"].pop()
            result["next_offset"] = offset + len(result["nodes"])
            result["truncated"] = True
        if len(encode(result).encode()) > MAX_OUTPUT and result["nodes"]:
            node = result["nodes"][0]
            result["nodes"] = [{key: node[key] for key in ("kind", "id", "status")} | {
                "details_omitted": True, "reason": "node_exceeds_response_budget"}]
            result["next_offset"] = offset + 1 if offset + 1 < len(nodes) else None
            result["truncated"] = True
        if len(encode(result).encode()) > MAX_OUTPUT:
            result["hypotheses"], result["criteria"], result["next_checks"] = [], [], []
            result["summary_details_omitted"] = True
        return result

    def cases(self, tags=None, limit=20, offset=0):
        request = _validate(RegressionCases, {"tags": [] if tags is None else tags, "limit": limit, "offset": offset})
        tags = set(request.tags)
        with self.guard.connect() as con:
            rows = con.execute("SELECT name,revision,body FROM investigations ORDER BY name").fetchall()
        cases = []
        for name, revision, raw in rows:
            body = json.loads(raw)
            for case in body["regressions"]:
                if tags.issubset(set(case["tags"])):
                    cases.append({"investigation": name, "revision": revision, "domain": body["domain"],
                                  **case, "status": "registered_case", "execution_observed": False})
        result = {"cases": cases[offset:offset + limit], "total": len(cases), "offset": offset,
                  "next_offset": offset + min(limit, max(0, len(cases) - offset)) if offset + limit < len(cases) else None,
                  "scope": "Case registry links notes to hypotheses and optional check profiles; registration does not execute or prove a test.",
                  "content_is_untrusted": True}
        while len(encode(result).encode()) > MAX_OUTPUT and result["cases"]:
            result["cases"].pop()
            result["next_offset"] = offset + len(result["cases"])
            result["truncated"] = True
        return result
