"""Nine executable modules, exposed through a compact progressive MCP facade."""
from __future__ import annotations

import json
import re
import time

from pydantic import ValidationError

from .guard import Engine, GuardError, encode, redact
from .index import CodeIndex, terms
from .state import State, clean
from .reducers import compress, log_groups, evaluate
from .schemas import QUERY_SCHEMAS, MANAGE_SCHEMAS
from .policy import RuntimePolicy
from . import __version__

HEADS = [
    {"id": 1, "name": "Orchestrator", "operations": ["plan"], "purpose": "Task route, risk cues and validation plan"},
    {"id": 2, "name": "Tool Router", "operations": ["route"], "purpose": "Progressive catalog and task-specific tool selection"},
    {"id": 3, "name": "Context Compiler", "operations": ["index", "context", "outline", "snippet", "impact", "verify"], "purpose": "Incremental parser index, ranked packets and local import graph"},
    {"id": 4, "name": "Project Memory", "operations": ["memory_save", "memory", "resume"], "purpose": "Provenanced constraints, decisions and source-aware resumption"},
    {"id": 5, "name": "Delta & Cache", "operations": ["remember_read", "delta", "cache_save", "cache"], "purpose": "Explicit snapshots, diffs and dependency-validated answer reuse"},
    {"id": 6, "name": "Budget Governor", "operations": ["session_open", "session_close", "health"], "purpose": "Runtime ownership, health and atomic response-byte budgets"},
    {"id": 7, "name": "Local Reducer", "operations": ["logs", "compress"], "purpose": "Grouped errors and loss-visible exact context deduplication"},
    {"id": 8, "name": "Usage & Evaluation", "operations": ["usage_record", "metrics", "evaluate"], "purpose": "Local telemetry, reported provider usage and paired quality checks"},
    {"id": 9, "name": "Scoped Handoff", "operations": ["handoff"], "purpose": "Bounded role/task briefs with project constraints and source evidence"},
]
PROFILES = {"economy": (4096, 1), "balanced": (12000, 3), "rigorous": (24576, 5)}


class Suite:
    def __init__(self, root, state_dir=None, policy=None):
        self.policy = policy or RuntimePolicy()
        self.guard = Engine(root, state_dir)
        self.index = CodeIndex(self.guard, self.policy)
        self.state = State(self.guard)

    def canonical(self, path):
        return self.guard.path(path).relative_to(self.guard.root).as_posix()

    def catalog(self, operation=""):
        if operation:
            self.policy.check(operation)
            schema = QUERY_SCHEMAS.get(operation) or MANAGE_SCHEMAS.get(operation)
            if not schema:
                raise GuardError("unknown operation")
            return {"operation": operation, "tool": "nexus_manage" if operation in MANAGE_SCHEMAS else "nexus_query",
                    "schema": schema.model_json_schema(), "writes_project_code": False}
        disabled = self.policy.disabled()
        heads = [{**head, "operations": [op for op in head["operations"] if op not in disabled],
                  "disabled_operations": [op for op in head["operations"] if op in disabled]} for head in HEADS]
        return {"project": "NEXUS9", "version": __version__, "heads": heads, "runtime_policy": self.policy.report(),
                "next": "Discover one operation schema with nexus_catalog(operation), then call its tool with parameters.",
                "limits": "UTF-8 response-byte budgets; provider token usage is not automatically observed"}

    def validate(self, operation, parameters, manage=False):
        self.policy.check(operation, parameters)
        schemas = MANAGE_SCHEMAS if manage else QUERY_SCHEMAS
        schema = schemas.get(operation)
        if not schema:
            raise GuardError("unknown operation; discover available schemas with nexus_catalog")
        if len(encode(parameters).encode()) > 65536:
            raise GuardError("parameter payload exceeds 64 KiB")
        try:
            return schema.model_validate(parameters).model_dump()
        except ValidationError as err:
            fields = [".".join(map(str, e["loc"])) for e in err.errors(include_input=False)][:8]
            raise GuardError("invalid parameters: " + ", ".join(fields)) from None

    def query(self, operation, parameters=None, session=None):
        started = time.monotonic()
        values = self.validate(operation, parameters or {})
        policy = self.state.session(session)
        limit = policy["call_budget"]
        if session and "profile" in values and "profile" not in (parameters or {}):
            values["profile"] = policy["profile"]
        try:
            if operation in {"context", "handoff", "compress"}:
                values["budget_bytes"] = min(values["budget_bytes"], limit)
            if operation == "health":
                with self.guard.connect() as con:
                    database_ok = con.execute("PRAGMA quick_check").fetchone()[0] == "ok"
                result = {"version": __version__, "state_integrity": "ok" if database_ok else "failed",
                          "runtime_policy": self.policy.report(), "project_bound": True,
                          "host_hooks_inspected": False, "scope": "local server only; run doctor.ps1 for IDE integration"}
            elif operation == "plan":
                result = self.plan(**values)
            elif operation == "index":
                result = self.index.refresh(**values)
            elif operation in {"context", "handoff"}:
                result = self.context(**values)
            elif operation == "route":
                result = self.route(**values)
            elif operation == "outline":
                path = self.canonical(values["path"])
                metadata, sha, _, changed = self.index.update_file(path)
                result = {"path": path, "sha256": sha, "reparsed": changed, **metadata, "content_is_untrusted": True}
            elif operation == "snippet":
                values["path"] = self.canonical(values["path"])
                result = self.index.snippet(**values)
            elif operation == "impact":
                result = self.impact(**values)
            elif operation == "verify":
                path = self.canonical(values["path"])
                if path.endswith((".py", ".json")):
                    result = self.guard.inspect(path, mode="syntax", max_bytes=self.policy.index_limits["file_bytes"])
                else:
                    meta, sha, _, _ = self.index.update_file(path)
                    result = {"path": path, "sha256": sha, "status": "fail" if meta["syntax_errors"] else "pass" if meta["parsed"] else "unsupported",
                              "scope": "Tree-sitter grammar syntax only; run compiler/type checker/tests"}
            elif operation == "logs":
                values["path"] = self.canonical(values["path"])
                result = log_groups(self.guard, **values)
            elif operation == "compress":
                result = compress(**values)
            elif operation == "delta":
                values["path"] = self.canonical(values["path"])
                result = self.state.delta(session, **values)
            elif operation in {"memory", "resume"}:
                result = self.state.memory(**values, resume=operation == "resume")
            elif operation == "cache":
                result = self.state.cache(**values)
            elif operation == "evaluate":
                result = evaluate(**values)
            else:
                result = self.state.metrics()
            result = clean(result)
            if len(encode(result).encode()) > limit:
                raise GuardError("result exceeds response budget; narrow the query, reduce count/groups, or explicitly increase the session budget")
            self.state.record(operation, result, started, session)
            return result
        except GuardError:
            self.state.record(operation, {"error": "guarded_failure"}, started, session, status="error", charge=False)
            raise

    def manage(self, operation, parameters=None, session=None):
        started = time.monotonic()
        values = self.validate(operation, parameters or {}, manage=True)
        if operation == "session_open":
            result = self.state.open(**values)
        elif operation == "session_close":
            result = self.state.close(**values)
        elif operation == "memory_save":
            result = self.state.memory_save(**values)
        elif operation == "remember_read":
            values["path"] = self.canonical(values["path"])
            result = self.state.remember(session, **values)
        elif operation == "cache_save":
            values["files"] = [self.canonical(p) for p in values["files"]]
            result = self.state.cache_save(**values)
        else:
            result = self.state.usage_record(values)
        # Management controls are not charged against retrieval budgets, so users can close exhausted sessions.
        self.state.record(operation, result, started, session, charge=False)
        return result

    def plan(self, task, profile="balanced"):
        lower = task.casefold()
        cues = {
            "database": ["sql", "database", "banco", "sqlite", "migration"],
            "web": ["pesquise", "web", "search online", "documentação oficial"],
            "version_control": ["commit", "branch", "git", "merge"],
            "debug": ["erro", "bug", "falha", "crash", "gps", "error"],
        }
        categories = [k for k, words in cues.items() if any(w in lower for w in words)] or ["code"]
        sensitive = any(w in lower for w in ("autentica", "pagamento", "segurança", "security", "delete", "excluir", "migration", "produção"))
        steps = ["context", "outline", "snippet"]
        if "debug" in categories:
            steps += ["logs", "impact"]
        if sensitive:
            steps += ["impact", "resume"]
        return {"task": redact(task), "categories": categories, "profile": profile,
                "risk_cues": "elevated" if sensitive else "ordinary_not_proof_of_low_risk", "operations": [op for op in dict.fromkeys(steps) if op not in self.policy.disabled()],
                "validation": ["compiler/type checker appropriate to project", "tests for affected behavior", "device test when hardware/location matters"],
                "method": "deterministic keyword policy; not model reasoning or automatic execution",
                "network_calls": 0, "spawns_agents": False}

    def route(self, task, profile="balanced", external_tools=None):
        plan = self.plan(task, profile)
        chosen = []
        for tool in external_tools or []:
            score = len(set(terms(task)) & set(terms(" ".join(tool["tags"]) + " " + tool["name"])))
            score += len(set(plan["categories"]) & set(tool["tags"])) * 3
            if score:
                chosen.append((score, tool))
        chosen.sort(key=lambda x: (-x[0], x[1]["schema_bytes"], x[1]["name"]))
        selected = [t for _, t in chosen[:3]]
        total = sum(t["schema_bytes"] for t in external_tools or [])
        return {"builtin_operations": plan["operations"], "suggested_external_tools": [t["name"] for t in selected],
                "declared_catalog_schema_bytes": total, "declared_selected_schema_bytes": sum(t["schema_bytes"] for t in selected),
                "changes_host_tool_loading": False, "method": "tag/keyword scoring over caller-supplied catalog",
                "note": "NEXUS exposes three fixed MCP tools; operation schemas are fetched on demand. Other servers are not reconfigured."}

    def impact(self, path, depth=1):
        path = self.canonical(path)
        refresh = self.index.ensure()
        self.index.update_file(path)
        files = self.index.files(required=[path])
        edges, unresolved = self.index.edges(files)
        frontier, affected = {path}, set()
        for _ in range(depth):
            next_frontier = {p for p, imports in edges.items() if set(imports) & frontier} - affected - {path}
            affected |= next_frontier
            frontier = next_frontier
        return {"path": path, "direct_imports": edges.get(path, []), "importers": sorted(affected)[:80],
                "unresolved_or_external_imports": unresolved.get(path, []), "index_limited": refresh["limited"] or self.index.files_limited,
                "index_cached": refresh["cached"], "index_age_seconds": refresh.get("age_seconds", 0),
                "truncated": len(affected) > 80, "graph": "static local import graph; no runtime call graph, TS aliases or dynamic imports resolution",
                "validation_required": True}

    def context(self, task, profile="balanced", paths=None, constraints=None, known_hashes=None,
                budget_bytes=12000, memory=None, focus_symbols=None, role=None, deliverable=None):
        cap, primary_count = PROFILES[profile]
        budget = min(cap, budget_bytes)
        canonical_paths = [self.canonical(p) for p in paths or []]
        wanted = set(terms(task))
        pinned = [redact(x) for x in constraints or []]
        saved_decisions = []
        if memory:
            remembered = self.state.memory(memory)
            if not remembered["found"]:
                raise GuardError("requested project memory does not exist")
            pinned += [f["text"] for f in remembered["body"]["constraints"]]
            saved_decisions = remembered["body"]["decisions"]
        packet = {"task": redact(task), "constraints": list(dict.fromkeys(pinned)), "decisions": saved_decisions,
                  "items": [], "omitted": [], "deduplicated": [], "coverage": {}, "content_is_untrusted": True,
                  "method": "lexical ranking + parser ranges + static local imports; not semantic embedding retrieval"}
        if role:
            packet.update(role=redact(role), deliverable=redact(deliverable), validation=["report actual checks and unresolved risks"],
                          launches_agent=False, changes_model=False)
        if len(encode(packet).encode()) > budget - 700:
            raise GuardError("task/constraints/decisions exceed packet budget; raise budget or explicitly revise memory")
        refresh = self.index.ensure()
        for path in canonical_paths:
            self.index.update_file(path)
        files = self.index.files(required=canonical_paths)
        rank = self.index.rank(task, files)
        primary = list(dict.fromkeys(canonical_paths + [p for p, _ in rank[:primary_count]]))[:12]
        # Revalidate selected content even when the discovery index has a short TTL.
        for path in primary:
            try:
                self.index.update_file(path)
            except (GuardError, OSError):
                continue
        dependencies = self.index.refresh_dependencies(primary)
        files = self.index.files(required=primary + dependencies)
        edges, unresolved = self.index.edges(files)
        secondary = list(dict.fromkeys(p for parent in primary for p in edges.get(parent, []) if p not in primary))[:24]
        source_bytes, represented, block_hashes, needed_names = 0, set(), {}, set()
        for path in primary + secondary:
            try:
                meta, sha, raw, _ = self.index.update_file(path)
            except (GuardError, OSError):
                packet["omitted"].append({"path": path, "reason": "source_unavailable"})
                continue
            source_bytes += len(raw.encode())
            if (known_hashes or {}).get(path) == sha:
                packet["deduplicated"].append({"path": path, "reason": "caller_explicitly_declared_hash_in_active_context", "sha256": sha})
                represented.add(path)
                continue
            lines = redact(raw).splitlines()
            focus = (focus_symbols or {}).get(path)
            symbols = meta["symbols"]
            if focus:
                symbols = [s for s in symbols if focus in (s["name"], s["qualified"])]
                if len(symbols) != 1:
                    packet["omitted"].append({"path": path, "reason": "focused_symbol_missing_or_ambiguous"})
                    continue
            else:
                symbols = sorted(symbols, key=lambda s: (-len(wanted & set(terms(s["qualified"] + " " + s["signature"]))), s["end"] - s["start"], s["start"]))[:2]
            if path in primary:
                referenced = {r for s in symbols for r in s.get("references", [])}
                needed_names |= referenced
                extra = [s for s in meta["symbols"] if s["name"] in referenced and s not in symbols][:5]
                symbols = symbols + extra
            blocks = []
            if path in secondary and not focus:
                blocks = [{"start": 1, "end": min(20, len(lines)), "kind": "dependency_outline",
                           "text": encode({"symbols": meta["symbols"][:12], "imports": meta["imports"][:12], "syntax_errors": meta["syntax_errors"]})}]
                for symbol in [s for s in meta["symbols"] if s["name"] in needed_names][:5]:
                    blocks.append({"start": symbol["start"], "end": symbol["end"], "kind": "dependency_symbol", "symbol": symbol["qualified"],
                                   "text": "\n".join(lines[symbol["start"] - 1:symbol["end"]])})
            elif symbols:
                for symbol in symbols:
                    blocks.append({"start": symbol["start"], "end": symbol["end"], "kind": "parser_symbol", "symbol": symbol["qualified"],
                                   "text": "\n".join(lines[symbol["start"] - 1:symbol["end"]])})
                spans = meta["import_ranges"][:12]
                header = "\n".join("\n".join(lines[span["start"] - 1:span["end"]]) for span in spans)
                if header:
                    blocks.insert(0, {"start": min(s["start"] for s in spans), "end": max(s["end"] for s in spans),
                                      "kind": "import_statements", "text": header})
            else:
                blocks = [{"start": 1, "end": min(60, len(lines)), "kind": "line_window", "text": "\n".join(lines[:60])}]
            for block in blocks:
                item = {"path": path, "sha256": sha, "syntax_errors": meta["syntax_errors"], **block}
                block_digest = __import__("hashlib").sha256(block["text"].encode()).hexdigest()
                if block_digest in block_hashes:
                    packet["deduplicated"].append({"path": path, "same_as": block_hashes[block_digest], "reason": "identical_selected_text_only"})
                    represented.add(path)
                    continue
                packet["items"].append(item)
                if len(encode(packet).encode()) > budget - 700:
                    packet["items"].pop()
                    packet["omitted"].append({"path": path, "symbol": block.get("symbol"), "reason": "whole_block_exceeds_budget"})
                else:
                    represented.add(path)
                    block_hashes[block_digest] = path
        required_missing = sorted(set(canonical_paths) - represented)
        packet["coverage"] = {"primary_paths": primary, "required_paths_missing": required_missing,
                              "index_limited": refresh["limited"] or self.index.files_limited, "source_bytes_examined": source_bytes,
                              "index_cached": refresh["cached"], "index_age_seconds": refresh.get("age_seconds", 0),
                              "selected_sources_hash_checked": True,
                              "unresolved_imports": {p: unresolved.get(p, [])[:10] for p in primary if unresolved.get(p)},
                              "incomplete": bool(required_missing or packet["omitted"] or refresh["limited"] or self.index.files_limited),
                              "selection_is_not_proof_of_complete_task_context": True}
        if len(encode(packet).encode()) > budget:
            # Do not silently remove constraints or evidence already selected.
            raise GuardError("packet metadata exceeds budget; narrow paths/task or increase budget")
        packet["local_budget_bytes"] = budget
        if len(encode(packet).encode()) > budget:
            raise GuardError("packet exceeds budget after accounting; increase budget")
        return packet
