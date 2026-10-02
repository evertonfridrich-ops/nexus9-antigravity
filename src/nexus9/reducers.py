"""Local loss-visible reduction: exact dedup, priority selection, grouped logs."""
import hashlib
import os
import re
import stat
import time

from .guard import GuardError, encode, redact


def compress(blocks, budget_bytes):
    if len({b["id"] for b in blocks}) != len(blocks):
        raise GuardError("block identifiers must be unique")
    result = {"blocks": [], "aliases": [], "omitted": [], "host_history_replaced": False,
              "method": "exact deduplication + priority selection; no abstractive semantic summary"}
    digests = {}
    for block in sorted(blocks, key=lambda b: (not b["pinned"], -b["priority"], b["id"])):
        if block["id"] in {b["id"] for b in result["blocks"]}:
            raise GuardError("block identifiers must be unique")
        text = redact(block["text"])
        digest = hashlib.sha256(text.encode()).hexdigest()
        if digest in digests:
            result["aliases"].append({"id": block["id"], "same_as": digests[digest]})
            continue
        item = {"id": block["id"], "text": text, "pinned": block["pinned"]}
        result["blocks"].append(item)
        if len(encode(result).encode()) > budget_bytes - 600:
            result["blocks"].pop()
            if block["pinned"]:
                raise GuardError("pinned content exceeds budget; it will not be silently discarded")
            result["omitted"].append(block["id"])
        else:
            digests[digest] = block["id"]
    result["input_bytes"] = sum(len(b["text"].encode()) for b in blocks)
    if len(encode(result).encode()) > budget_bytes:
        raise GuardError("reduction metadata exceeds budget; use fewer blocks")
    return result


def log_groups(guard, path, max_groups, include_warnings):
    file = guard.path(path)
    groups, scanned, bytes_read, limited = {}, 0, 0, False
    started = time.monotonic()
    fd = os.open(file, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1:
            raise GuardError("unsafe log type")
        private_key = False
        while True:
            raw = stream.readline(16385)
            if not raw:
                break
            bytes_read += len(raw)
            if bytes_read > 64 * 1024 * 1024 or time.monotonic() - started > 10.0:
                limited = True
                break
            if b"\x00" in raw:
                raise GuardError("binary log denied")
            if len(raw) > 16384 and not raw.endswith(b"\n"):
                # Drain the whole oversized physical line without fragmenting it into fake events.
                limited = True
                while raw and not raw.endswith(b"\n"):
                    raw = stream.readline(16385)
                    bytes_read += len(raw)
                    if bytes_read > 64 * 1024 * 1024 or time.monotonic() - started > 3:
                        break
                if bytes_read > 64 * 1024 * 1024 or time.monotonic() - started > 3:
                    break
                scanned += 1
                continue
            scanned += 1
            try:
                line = raw.decode("utf-8-sig").rstrip()
            except UnicodeError:
                raise GuardError("log must be UTF-8") from None
            if "-----BEGIN " in line and "PRIVATE KEY-----" in line:
                private_key = True
            if private_key:
                if "-----END " in line and "PRIVATE KEY-----" in line:
                    private_key = False
                continue
            line = redact(line)
            levels = r"error|fatal|exception|failed|critical|traceback" + (r"|warn" if include_warnings else "")
            if not re.search(levels, line, re.I):
                continue
            normalized = re.sub(r"\b\d{4}-\d\d-\d\d[T ][0-9:.+Z-]+", "<timestamp>", line)
            normalized = re.sub(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b|\b0x[0-9a-f]+\b", "<id>", normalized, flags=re.I)
            normalized = re.sub(r"\b\d{6,}\b", "<large-number>", normalized)
            normalized = normalized[:1000]
            if normalized not in groups:
                if len(groups) >= 500:
                    limited = True
                    continue
                groups[normalized] = {"pattern": normalized, "count": 0, "first_line": scanned, "last_line": scanned, "sample": line[:1000]}
            groups[normalized]["count"] += 1
            groups[normalized]["last_line"] = scanned
    selected = sorted(groups.values(), key=lambda g: (-g["count"], g["first_line"]))[:max_groups]
    return {"path": path, "groups": selected, "scanned_lines": scanned, "bytes_scanned": bytes_read,
            "distinct_groups": len(groups), "limited": limited or len(groups) > max_groups,
            "method": "severity filter + timestamps/IDs normalization; small status codes preserved", "content_is_untrusted": True}


def evaluate(trials):
    paired = {}
    for trial in trials:
        pair = paired.setdefault(trial["task_id"], {})
        if trial["variant"] in pair:
            raise GuardError("duplicate task/variant in evaluation")
        pair[trial["variant"]] = trial
    if any(set(pair) != {"baseline", "nexus"} for pair in paired.values()):
        raise GuardError("each task requires baseline and nexus trials")
    baseline = sum(p["baseline"]["input_tokens"] + p["baseline"]["output_tokens"] for p in paired.values())
    candidate = sum(p["nexus"]["input_tokens"] + p["nexus"]["output_tokens"] for p in paired.values())
    regressions = [task for task, p in paired.items() if p["baseline"]["passed"] and not p["nexus"]["passed"]]
    return {"paired_tasks": len(paired), "reported_baseline_tokens": baseline, "reported_nexus_tokens": candidate,
            "reported_token_reduction_percent": round(100 * (baseline - candidate) / baseline, 2) if baseline else None,
            "quality_regressions": regressions, "acceptable_on_supplied_checks": not regressions,
            "source": "caller-supplied trials; not an independently executed model benchmark",
            "cost_savings": None}
