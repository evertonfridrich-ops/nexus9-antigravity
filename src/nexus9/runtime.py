"""Observable server identity and on-disk drift; no claims about model adherence."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import uuid

from . import __version__
from .guard import encode


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class RuntimeIdentity:
    def __init__(self, package_root=None):
        self.package_root = Path(package_root) if package_root else Path(__file__).parent
        self.instance_id = uuid.uuid4().hex
        self.started_at = utc_now()
        self.version = __version__
        self.startup = self._fingerprint()
        self.last_context_delivery = None

    def _fingerprint(self):
        try:
            files = sorted(self.package_root.glob("*.py"))
            if len(files) > 100:
                return None
            total, hashes = 0, {}
            for path in files:
                if path.is_symlink() or not path.is_file():
                    return None
                total += path.stat().st_size
                if total > 8 * 1024 * 1024:
                    return None
                hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
            return hashlib.sha256(encode(hashes).encode()).hexdigest() if hashes else None
        except OSError:
            return None

    def delivered(self, operation, packet):
        self.last_context_delivery = {"receipt_id": uuid.uuid4().hex, "operation": operation,
            "at": utc_now(), "payload_sha256": hashlib.sha256(encode(packet).encode()).hexdigest(),
            "scope": "Payload returned by this endpoint; not proof of model comprehension or adherence."}

    def status(self):
        current = self._fingerprint()
        return {"version": self.version, "instance_id": self.instance_id, "started_at": self.started_at,
                "observed_at": utc_now(), "files_at_startup_sha256": self.startup,
                "current_files_sha256": current,
                "restart_required": self.startup is None or current is None or self.startup != current,
                "last_context_delivery": self.last_context_delivery,
                "host_skill_loaded_verified": False, "model_adherence_verified": False,
                "automatic_update": False,
                "scope": "Imported version plus file fingerprints, not an attestation of loaded bytecode. A real call identifies the responding server instance."}
