"""Bounded integration audit, backed-up installation and ownership-aware rollback.

Only stdlib. Reports omit MCP commands, arguments, environment and rule contents.
File replacement is atomic; multiple files are journaled, not a filesystem transaction.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

from configure import unique_object, reject_constant

MAX_CONFIG = 2 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def load_json(data):
    return json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique_object, parse_constant=reject_constant)


def read_config(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("config must not be a symbolic link")
    if path.exists() and path.stat().st_size > MAX_CONFIG:
        raise ValueError("MCP config exceeds 2 MiB")
    original = path.read_bytes() if path.exists() else None
    data = load_json(original) if original is not None else {}
    if not isinstance(data, dict) or not isinstance(data.get("mcpServers", {}), dict):
        raise ValueError("config and mcpServers must be JSON objects")
    return original, data


def verify_package(package):
    package = Path(package).resolve()
    manifest = load_json((package / "MANIFEST.sha256.json").read_bytes())
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError("invalid release manifest")
    for name, expected in manifest.items():
        parts = Path(name).parts
        if Path(name).is_absolute() or ".." in parts or "\\" in name or ":" in name:
            raise ValueError("unsafe manifest member")
        file = package / name
        if file.is_symlink() or not file.is_file() or not file.resolve().is_relative_to(package):
            raise ValueError("missing or unsafe release file")
        if not isinstance(expected, str) or digest(file.read_bytes()) != expected:
            raise ValueError("release integrity verification failed")
    required = {"install.ps1", "src/nexus9/server.py", "src/nexus9/policy.py", "integration.py",
                "configure.py", "requirements.lock.txt", "skills/nexus9/SKILL.md", "scripts/smoke.py"}
    if not required.issubset(manifest):
        raise ValueError("release manifest lacks required files")
    for base in ("src", "skills", "scripts"):
        for file in (package / base).rglob("*"):
            if file.is_file() and "__pycache__" not in file.parts and file.suffix not in {".pyc", ".pyo"}:
                if file.relative_to(package).as_posix() not in manifest:
                    raise ValueError("unmanifested executable or Skill resource")
    return {"verified_files": len(manifest), "manifest_sha256": digest((package / "MANIFEST.sha256.json").read_bytes()),
            "scope": "integrity against bundled manifest; not publisher signature"}


def audit(config, home, workspace, skill_dir=None):
    _, data = read_config(config)
    servers, hydra, memory = [], [], []
    for name, entry in data.get("mcpServers", {}).items():
        if not isinstance(entry, dict):
            continue
        active = entry.get("disabled") is not True
        # Inspect identifiers in memory; never include their values in a report.
        identifiers = " ".join([name, str(entry.get("command", "")), *map(str, entry.get("args", []))]).casefold()
        servers.append({"name": name, "configured_enabled": active})
        if active and "hydra" in identifiers:
            hydra.append(name)
        if active and any(tag in identifiers for tag in ("agentmemory", "agent-memory", "agent_memory")):
            memory.append(name)
    home, workspace = Path(home), Path(workspace)
    candidates = [home / ".gemini/GEMINI.md", workspace / "GEMINI.md", workspace / "AGENTS.md"]
    locations = [home / ".gemini/config/rules", home / ".gemini/antigravity/rules",
                 home / ".gemini/config/hooks", home / ".gemini/antigravity/hooks",
                 workspace / ".agents/rules", workspace / ".agents/hooks"]
    # Common settings are inspected only for strings that may identify hooks/rules.
    candidates += [home / ".gemini/settings.json", home / ".gemini/config/settings.json",
                   home / ".gemini/antigravity/settings.json", workspace / ".agents/settings.json"]
    limited, findings, visited = False, [], 0
    for base in locations:
        if not base.is_dir() or base.is_symlink():
            continue
        for directory, dirs, files in os.walk(base, followlinks=False):
            dirs[:] = [name for name in dirs if not (Path(directory) / name).is_symlink()]
            for name in files:
                visited += 1
                if visited > 200:
                    limited = True
                    break
                candidates.append(Path(directory) / name)
            if limited:
                break
        if limited:
            break
    total = 0
    for file in list(dict.fromkeys(candidates))[:212]:
        if not file.is_file() or file.is_symlink() or file.suffix.lower() not in {".md", ".json", ".yaml", ".yml", ".toml"}:
            continue
        try:
            size = file.stat().st_size
            if size > 256 * 1024 or total + size > 2 * 1024 * 1024:
                limited = True
                continue
            text = file.read_bytes().decode("utf-8-sig", errors="replace").casefold()
            total += size
        except OSError:
            limited = True
            continue
        tags = [tag for tag in ("hydra", "agentmemory", "nexus9") if tag in text or tag in file.name.casefold()]
        if tags:
            findings.append({"path": str(file), "mentions": tags, "active_status": "requires IDE inspection"})
    hydra_rules = any("hydra" in finding["mentions"] for finding in findings)
    memory_owner = "external" if memory or hydra or hydra_rules else "nexus9"
    compression_owner = "external" if hydra or hydra_rules else "nexus9"
    skill = Path(skill_dir) if skill_dir else home / ".gemini/config/skills/nexus9"
    return {"config_path": str(config), "workspace": str(workspace), "servers": servers,
            "hydra_candidates": hydra, "agent_memory_candidates": memory, "rule_hook_candidates": findings,
            "scan_limited": limited, "recommended_memory_owner": memory_owner,
            "recommended_compression_owner": compression_owner, "skill_path": str(skill / "SKILL.md"),
            "skill_present": (skill / "SKILL.md").is_file(),
            "note": "Configured enabled is not live connection status. Rule mentions are candidates, not proof of active hooks. No other server or hook is changed."}


def atomic_write(path, payload, expected):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("managed file must not be a symbolic link")
    current = path.read_bytes() if path.exists() else None
    if current != expected:
        raise ValueError("managed file changed concurrently")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix="nexus9-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if (path.read_bytes() if path.exists() else None) != expected:
            raise ValueError("managed file changed concurrently")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def build_changes(registration, package, config):
    name, entry = registration["name"], registration["entry"]
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", name) or not isinstance(entry, dict):
        raise ValueError("invalid registration")
    original, data = read_config(config)
    servers = data.setdefault("mcpServers", {})
    if name in servers and servers[name] != entry and not registration.get("replace"):
        raise ValueError("NEXUS server name already exists with another configuration; explicit replacement required")
    servers[name] = entry
    desired = json_bytes(data)
    changes = [(Path(config), original, desired, "config")]
    source = Path(package) / "skills/nexus9"
    target = Path(registration["skill_dir"])
    if not (source / "SKILL.md").is_file():
        raise ValueError("native Skill missing from package")
    for file in sorted(source.rglob("*")):
        if not file.is_file():
            continue
        if file.is_symlink():
            raise ValueError("unsafe Skill source")
        path = target / file.relative_to(source)
        before = path.read_bytes() if path.exists() else None
        after = file.read_bytes()
        if before is not None and before != after and not registration.get("replace"):
            raise ValueError("existing Skill differs; explicit replacement required")
        changes.append((path, before, after, "skill"))
    if registration.get("install_rule"):
        path = Path(registration["workspace"]) / ".agents/rules/nexus9.md"
        before = path.read_bytes() if path.exists() else None
        after = (Path(package) / "rules/nexus9.md").read_bytes()
        if before is not None and before != after and not registration.get("replace"):
            raise ValueError("existing rule differs; explicit replacement required")
        changes.append((path, before, after, "rule"))
    # Avoid reformatting unchanged config and creating empty installation receipts.
    if original is not None and load_json(original) == data:
        changes[0] = (Path(config), original, original, "config")
    return [change for change in changes if change[1] != change[2]]


def install(registration, package, config, receipt_dir):
    changes = build_changes(registration, package, config)
    if not changes:
        return {"status": "unchanged", "receipt": None, "changed_files": 0}
    directory = Path(receipt_dir) / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12])
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    receipt_path = directory / "receipt.json"
    receipt = {"format": 1, "status": "applying", "server_name": registration["name"],
               "installed_entry": registration["entry"], "files": []}
    for i, (path, before, after, kind) in enumerate(changes):
        backup = directory / (str(i) + ".backup") if before is not None else None
        if backup:
            atomic_write(backup, before, None)
        receipt["files"].append({"path": str(path.absolute()), "kind": kind, "before_sha256": digest(before),
                                 "after_sha256": digest(after), "backup": str(backup.absolute()) if backup else None})
    atomic_write(receipt_path, json_bytes(receipt), None)
    applied = []
    try:
        for path, before, after, kind in changes:
            atomic_write(path, after, before)
            applied.append((path, before, after))
    except (OSError, ValueError):
        rollback_conflicts = []
        for path, before, after in reversed(applied):
            try:
                if (path.read_bytes() if path.exists() else None) != after:
                    raise ValueError("concurrent modification")
                if before is None:
                    path.unlink()
                else:
                    atomic_write(path, before, after)
            except (OSError, ValueError):
                rollback_conflicts.append(str(path))
        receipt["status"] = "recovery_required" if rollback_conflicts else "rolled_back"
        receipt["recovery_paths"] = rollback_conflicts
        previous = receipt_path.read_bytes()
        atomic_write(receipt_path, json_bytes(receipt), previous)
        raise ValueError("installation failed; recovery receipt: " + str(receipt_path)) from None
    receipt["status"] = "installed"
    atomic_write(receipt_path, json_bytes(receipt), receipt_path.read_bytes())
    return {"status": "installed", "receipt": str(receipt_path), "changed_files": len(changes)}


def rollback(receipt_path):
    receipt_path = Path(receipt_path).resolve()
    receipt = load_json(receipt_path.read_bytes())
    if receipt.get("format") != 1 or receipt.get("status") not in {"installed", "applying", "recovery_required"}:
        raise ValueError("receipt is not eligible for rollback")
    changes = []
    for record in reversed(receipt["files"]):
        path = Path(record["path"])
        if not path.is_absolute() or path.is_symlink():
            raise ValueError("unsafe receipt path")
        current = path.read_bytes() if path.exists() else None
        before = None
        if record["backup"]:
            backup = Path(record["backup"]).resolve()
            if not backup.is_relative_to(receipt_path.parent):
                raise ValueError("backup outside receipt directory")
            before = backup.read_bytes()
        if digest(before) != record["before_sha256"]:
            raise ValueError("backup integrity mismatch")
        if digest(current) == record["before_sha256"]:
            continue  # Failed installation may already have restored this file.
        if digest(current) != record["after_sha256"]:
            if record["kind"] != "config" or current is None:
                raise ValueError("managed file changed after installation; review it before rollback")
            _, now = read_config(path)
            old = load_json(before) if before is not None else {}
            servers = now.get("mcpServers", {})
            expected = servers.get(receipt["server_name"])
            # Reconstruct the installed NEXUS entry from the registration journal.
            installed_entry = receipt.get("installed_entry")
            if installed_entry is None or expected != installed_entry:
                raise ValueError("NEXUS entry changed; rollback refused")
            previous_servers = old.get("mcpServers", {})
            if receipt["server_name"] in previous_servers:
                servers[receipt["server_name"]] = previous_servers[receipt["server_name"]]
            else:
                servers.pop(receipt["server_name"], None)
            if not servers and "mcpServers" not in old:
                now.pop("mcpServers", None)
            before = json_bytes(now)
        changes.append((path, current, before))
    for path, current, before in changes:
        if before is None:
            if path.read_bytes() != current:
                raise ValueError("managed file changed concurrently")
            path.unlink()
        else:
            atomic_write(path, before, current)
    receipt["status"] = "rolled_back"
    atomic_write(receipt_path, json_bytes(receipt), receipt_path.read_bytes())
    return {"status": "rolled_back", "restored_files": len(changes), "receipt": str(receipt_path)}


def main():
    parser = argparse.ArgumentParser(description="NEXUS9 local installation integration")
    parser.add_argument("action", choices=("doctor", "verify", "preflight", "install", "rollback"))
    parser.add_argument("--config")
    parser.add_argument("--home")
    parser.add_argument("--workspace")
    parser.add_argument("--skill-dir")
    parser.add_argument("--package", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--registration")
    parser.add_argument("--receipt-dir")
    parser.add_argument("--receipt")
    args = parser.parse_args()
    try:
        if args.action == "verify":
            result = verify_package(args.package)
        elif args.action == "doctor":
            if not args.config or not args.home or not args.workspace:
                raise ValueError("doctor requires config, home and workspace")
            result = audit(args.config, args.home, args.workspace, args.skill_dir)
        elif args.action == "rollback":
            result = rollback(args.receipt)
        else:
            registration = load_json(Path(args.registration).read_bytes())
            if args.action == "preflight":
                changes = build_changes(registration, args.package, args.config)
                result = {"status": "ready", "writes": [{"path": str(p), "kind": kind} for p, _, _, kind in changes]}
            else:
                result = install(registration, args.package, args.config, args.receipt_dir)
        print(json.dumps(result, ensure_ascii=True))
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(1, "Integration failed: check paths, valid unique-key JSON, release integrity, existing-file conflicts and permissions. Installation receipts contain recovery information.\n")


if __name__ == "__main__":
    main()
