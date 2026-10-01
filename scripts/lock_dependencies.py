"""Generate a cross-platform, hash-verified lock from the tested resolved versions.

PyPI release metadata supplies hashes for all published wheels/sdists, not just
the local Linux wheel. This script is a development utility, never run at install.
"""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
lines = (ROOT / "requirements.resolved.txt").read_text().splitlines()
packages = [(line.split("==")[0], line.split("==")[1], "") for line in lines if "==" in line]
packages.append(("colorama", "0.4.6", '; sys_platform == "win32"'))
packages.append(("pywin32", "311", '; sys_platform == "win32"'))


def fetch(package):
    name, version, marker = package
    with urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30) as response:
        metadata = json.load(response)
    digests = sorted({x["digests"]["sha256"] for x in metadata["urls"] if not x.get("yanked")})
    if not digests:
        raise ValueError(f"No hashes available for {name}=={version}")
    return name + "==" + version + marker + " \\\n" + " \\\n".join("    --hash=sha256:" + digest for digest in digests)


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=8) as pool:
        blocks = list(pool.map(fetch, sorted(packages)))
    (ROOT / "requirements.lock.txt").write_text("# Tested versions; all non-yanked release hashes from PyPI.\n" + "\n".join(blocks) + "\n")
    print(f"Locked {len(packages)} packages including Windows-specific packages.")
