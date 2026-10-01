"""Offline executable acceptance scenario. Synthetic fixture, no provider billing."""
import asyncio
import json
from pathlib import Path
import tempfile

from nexus9.guard import encode
from nexus9.server import make_server
from nexus9.suite import Suite
from nexus9.schemas import QUERY_SCHEMAS, MANAGE_SCHEMAS


async def run():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp) / "project"
        root.mkdir()
        gps = root / "gps.ts"
        source = ("// unrelated build explanation\n" * 3000 +
                  "import { locate } from './location';\n" +
                  "const gpsOptions = { distanceInterval: 1, timeInterval: 1000 };\n" +
                  "export const startGPS = () => locate(gpsOptions);\n")
        gps.write_text(source)
        (root / "location.ts").write_text("export function locate(options: { distanceInterval: number }) { return options.distanceInterval; }\n")
        (root / "errors.log").write_text("2026-10-01T01:00:00Z ERROR GPS timeout 100123\n" * 4000)
        suite = Suite(root, Path(temp) / "state")
        suite.manage("session_open", {"name": "gps"})
        packet = suite.query("context", {"task": "Fix startGPS", "paths": ["gps.ts"],
            "focus_symbols": {"gps.ts": "startGPS"}, "constraints": ["Keep Expo 52 and React Native 0.76.9"]}, session="gps")
        all_text = "\n".join(i["text"] for i in packet["items"])
        checks = {
            "target_function_present": "startGPS = () => locate" in all_text,
            "referenced_options_present": "timeInterval: 1000" in all_text,
            "local_dependency_body_present": "return options.distanceInterval" in all_text,
            "constraint_preserved": "Keep Expo 52 and React Native 0.76.9" in packet["constraints"],
            "within_budget": len(encode(packet).encode()) <= 12000,
        }
        suite.manage("remember_read", {"path": "location.ts"}, session="gps")
        (root / "location.ts").write_text("export function locate(options: { distanceInterval: number }) { return options.distanceInterval + 1; }\n")
        diff = suite.query("delta", {"path": "location.ts"}, session="gps")
        logs = suite.query("logs", {"path": "errors.log"})
        checks.update(delta_detected=not diff["unchanged"], log_repetitions_grouped=logs["groups"][0]["count"] == 4000)
        facade = await make_server(suite).list_tools()
        declared_schemas = {k: v.model_json_schema() for k, v in {**QUERY_SCHEMAS, **MANAGE_SCHEMAS}.items()}
        report = {
            "kind": "offline synthetic acceptance scenario; not model outcome or billing benchmark",
            "heads": 9, "operations": len(declared_schemas), "fixed_mcp_tools": len(facade),
            "checks": checks, "source_file_utf8_bytes": len(source.encode()),
            "context_packet_utf8_bytes": len(encode(packet).encode()),
            "facade_input_schema_bytes": sum(len(encode(t.inputSchema).encode()) for t in facade),
            "all_operation_input_schema_bytes": sum(len(encode(v).encode()) for v in declared_schemas.values()),
            "log_source_utf8_bytes": (root / "errors.log").stat().st_size,
            "log_report_utf8_bytes": len(encode(logs).encode()),
            "actual_provider_token_savings": None, "actual_cost_savings": None,
            "context_packet": packet,
        }
        assert all(checks.values()), checks
        return report


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), ensure_ascii=False, indent=2))
