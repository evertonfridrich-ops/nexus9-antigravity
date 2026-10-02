"""Local execution policy. Ownership is enforced before state access."""
from dataclasses import dataclass

from .guard import GuardError


@dataclass(frozen=True)
class RuntimePolicy:
    hardware: str = "standard"
    memory_owner: str = "nexus9"
    compression_owner: str = "nexus9"

    def __post_init__(self):
        if self.hardware not in {"light", "standard"}:
            raise GuardError("unknown hardware profile")
        if self.memory_owner not in {"nexus9", "external"} or self.compression_owner not in {"nexus9", "external"}:
            raise GuardError("unknown capability owner")

    @property
    def index_limits(self):
        if self.hardware == "light":
            return {"max_files": 120, "max_reparsed": 24, "seconds": 2.0,
                    "source_bytes": 8 * 1024 * 1024, "file_bytes": 512 * 1024,
                    "scan_entries": 1200, "scan_seconds": 1.0, "refresh_ttl": 30.0,
                    "inventory_records": 512}
        return {"max_files": 1000, "max_reparsed": 1000, "seconds": 30.0,
                "source_bytes": 64 * 1024 * 1024, "file_bytes": 2 * 1024 * 1024,
                "scan_entries": 5000, "scan_seconds": 10.0, "refresh_ttl": 0.0,
                "inventory_records": 5000}

    def disabled(self):
        operations = {}
        if self.memory_owner == "external":
            operations.update({op: "memory owned by external server" for op in ("memory_save", "memory", "resume")})
        if self.compression_owner == "external":
            operations.update({op: "compression owned by external server" for op in ("compress", "logs")})
        return operations

    def check(self, operation, parameters=None):
        reason = self.disabled().get(operation)
        if reason:
            raise GuardError("operation disabled by runtime policy: " + reason)
        if operation in {"context", "handoff"} and (parameters or {}).get("memory") and self.memory_owner == "external":
            raise GuardError("NEXUS memory reference disabled; pass verified external constraints explicitly")

    def report(self):
        return {"hardware": self.hardware, "memory_owner": self.memory_owner,
                "compression_owner": self.compression_owner, "disabled_operations": self.disabled(),
                "index_limits": self.index_limits, "background_workers": 0,
                "embeddings": False, "outbound_network": False,
                "deadlines_are_cooperative": True}
