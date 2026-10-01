"""Offline CPU/time measurements on a synthetic corpus; no model/billing claims."""
import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time

from nexus9.guard import encode
from nexus9.policy import RuntimePolicy
from nexus9.suite import Suite


def benchmark(files, repeats):
    with tempfile.TemporaryDirectory(prefix="nexus9-benchmark-") as temp:
        root = Path(temp) / "project"
        root.mkdir()
        for i in range(files):
            (root / f"noise{i:03}.py").write_text("# unrelated build notes\n" * 2000 + f"def noise{i}():\n    return {i}\n")
        (root / "main.py").write_text("from dep import answer\ndef calculate():\n    return answer()\n")
        (root / "dep.py").write_text("def answer():\n    return 99\n")
        suite = Suite(root, Path(temp) / "state", RuntimePolicy("light", "external", "external"))
        samples = []
        for i in range(repeats):
            started, cpu = time.perf_counter(), time.process_time()
            result = suite.query("context", {"task": "Inspect calculate", "paths": ["main.py"],
                "focus_symbols": {"main.py": "calculate"}, "constraints": ["Preserve behavior until tested"]})
            samples.append({"phase": "cold" if i == 0 else "warm", "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                            "process_cpu_ms": round((time.process_time() - cpu) * 1000, 3),
                            "output_bytes": len(encode(result).encode()), "index_cached": result["coverage"]["index_cached"],
                            "coverage_incomplete": result["coverage"]["incomplete"]})
            assert any("return 99" in item["text"] for item in result["items"])
        return {"scope": "synthetic local Suite benchmark; not Antigravity, user CPU, model quality or billing",
                "platform": platform.platform(), "python": sys.version.split()[0], "logical_cpus_in_runner": os.cpu_count(),
                "hardware_policy": suite.policy.report(), "files": files + 2,
                "corpus_bytes": sum(file.stat().st_size for file in root.iterdir()),
                "samples": samples, "warm_median_elapsed_ms": statistics.median(sample["elapsed_ms"] for sample in samples[1:]),
                "warm_median_cpu_ms": statistics.median(sample["process_cpu_ms"] for sample in samples[1:]),
                "source_and_dependency_checks": "passed"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", type=int, choices=range(1, 201), default=80)
    parser.add_argument("--repeats", type=int, choices=range(2, 21), default=6)
    args = parser.parse_args()
    print(json.dumps(benchmark(args.files, args.repeats), indent=2))
