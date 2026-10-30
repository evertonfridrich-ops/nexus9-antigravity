"""Create a source-only ZIP and verify every packaged member's SHA-256."""
import hashlib
import json
from pathlib import Path
import zipfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE = {"__pycache__", ".venv", ".git", "dist", "build", ".pytest_cache"}


def members():
    return sorted(p for p in ROOT.rglob("*") if p.is_file()
                  and not any(part in EXCLUDE or part.endswith(".egg-info") for part in p.relative_to(ROOT).parts)
                  and not p.name.endswith((".pyc", ".pyo"))
                  and p.name not in {"MANIFEST.sha256.json", "uv.lock"})


if __name__ == "__main__":
    manifest = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in members()}
    manifest_path = ROOT / "MANIFEST.sha256.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    archive = ROOT.parent / f"NEXUS9-Antigravity-{version}-Windows.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted([*members(), manifest_path]):
            info = zipfile.ZipInfo("nexus9/" + p.relative_to(ROOT).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, p.read_bytes(), compresslevel=9)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for name, digest in manifest.items():
            assert hashlib.sha256(z.read("nexus9/" + name)).hexdigest() == digest
    print(json.dumps({"path": str(archive), "bytes": archive.stat().st_size,
                      "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "files": len(manifest) + 1}))
