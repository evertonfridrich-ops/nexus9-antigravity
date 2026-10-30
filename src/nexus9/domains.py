"""Metadata-only domain recipes; never load plugin code or contact other MCPs."""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .guard import GuardError, encode
from .state import clean

Name = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
Brief = Annotated[str, Field(min_length=1, max_length=500)]


class Recipe(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: Name
    title: Brief
    scope: Brief
    invariants: Annotated[list[Brief], Field(max_length=12)] = []
    evidence: Annotated[list[Brief], Field(max_length=12)] = []
    external_tools: Annotated[list[Name], Field(max_length=12)] = []


class RecipeFile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["1.0"]
    packs: Annotated[list[Recipe], Field(max_length=10)]


class DomainQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: Annotated[str, Field(pattern=r"^$|^[A-Za-z0-9_-]{1,64}$")] = ""


BUILTINS = [
    {"id": "generic", "title": "Software investigation", "scope": "Declared source dependencies and explicit acceptance criteria.",
     "invariants": ["Preserve project constraints and user changes.", "Separate caller assessment, observed file fingerprints and observed test runs."],
     "evidence": ["Affected sources and reproducible observations", "Checks appropriate to the changed behavior"], "external_tools": []},
    {"id": "crypto-institutional", "title": "Crypto engineering", "scope": "Optional companion recipe for Crypto Institutional / QUANT9; no automatic connection.",
     "invariants": ["An order timeout does not establish rejection.", "Preserve distinct real fills and the current operating mode.", "Engineering checks do not establish profitability or authorize live trading."],
     "evidence": ["Sanitized replay/execution export and its source dependencies", "Temporal causality, ledger and recovery regressions"],
     "external_tools": ["crypto_catalog", "crypto_schema", "crypto_audit"]},
]


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


class Domains:
    def __init__(self, guard):
        self.guard = guard

    def get(self, name=""):
        rows = [dict(row) for row in BUILTINS]
        source_sha = None
        # The optional file lives only in the bound workspace, under guard policy.
        if (self.guard.root / "nexus9-domains.json").exists():
            _, raw, source_sha, size = self.guard.load("nexus9-domains.json")
            if size > 16384:
                raise GuardError("domain metadata exceeds 16 KiB")
            try:
                document = RecipeFile.model_validate(json.loads(raw, object_pairs_hook=_unique))
            except (ValueError, ValidationError, RecursionError):
                raise GuardError("invalid domain metadata; consult the documented schema") from None
            seen = {row["id"] for row in rows}
            for pack in document.packs:
                if pack.id in seen:
                    raise GuardError("domain identifiers must be unique; built-in recipes cannot be replaced")
                seen.add(pack.id)
                rows.append(pack.model_dump())
        selected = [row for row in rows if not name or row["id"] == name]
        if name and not selected:
            raise GuardError("domain recipe not found")
        return clean({"packs": selected, "metadata_sha256": source_sha,
                      "recipe_sha256": hashlib.sha256(encode(selected).encode()).hexdigest(),
                      "content_is_untrusted": True, "executes_plugin_code": False,
                      "external_tools_verified": False, "changes_host_tools": False,
                      "scope": "Recipes guide the agent; named tools must be discovered in the host before use."})
