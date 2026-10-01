"""Atomic config merge. Refuse invalid JSON, duplicates and silent replacement."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key in MCP config; resolve it before installation")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("non-finite values are not valid JSON")


def merge(config: Path, name: str, entry: dict, replace: bool = False):
    original = config.read_bytes() if config.exists() else None
    data = json.loads(original.decode("utf-8-sig"), object_pairs_hook=unique_object, parse_constant=reject_constant) if original is not None else {}
    if not isinstance(data, dict) or not isinstance(data.get("mcpServers", {}), dict):
        raise ValueError("config and mcpServers must be JSON objects")
    servers = data.setdefault("mcpServers", {})
    if name in servers and servers[name] != entry and not replace:
        raise ValueError("server name already registered; use another name or explicit replacement")
    if servers.get(name) == entry:
        return None
    servers[name] = entry
    payload = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    config.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if original is not None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = config.with_name(config.name + "." + stamp + ".bak")
        with backup.open("xb") as stream:
            stream.write(original)
    fd, temporary = tempfile.mkstemp(prefix="contextguard-", suffix=".tmp", dir=config.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # Detect common concurrent edits; no interprocess locking of unrelated IDE writers.
        current = config.read_bytes() if config.exists() else None
        if current != original:
            raise ValueError("config changed during installation; retry after closing its editor")
        os.replace(temporary, config)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return backup


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--registration", required=True)
    args = parser.parse_args()
    try:
        registration = json.loads(Path(args.registration).read_text(encoding="utf-8-sig"))
        backup = merge(Path(args.config), registration["name"], registration["entry"], registration["replace"])
        print("MCP config saved." + (" Backup: " + str(backup) if backup else ""))
    except (OSError, ValueError, KeyError):
        parser.exit(1, "Config merge failed: check valid unique-key JSON, server name conflicts, file permissions and concurrent edits.\n")
