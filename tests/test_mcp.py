import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPTests(unittest.TestCase):
    def test_real_mcp_workflow_and_single_result_representation(self):
        async def scenario(root, state):
            params = StdioServerParameters(command=sys.executable,
                args=["-m", "nexus9.server", "--root", str(root), "--state-dir", str(state)],
                env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")})
            async def call(session, name, arguments):
                result = await session.call_tool(name, arguments)
                self.assertFalse(result.isError, result.content)
                self.assertIsNone(result.structuredContent) # No duplicate JSON payload in the envelope.
                self.assertEqual(len(result.content), 1)
                return json.loads(result.content[0].text)
            with anyio.fail_after(30):
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as client:
                        initialized = await client.initialize()
                        self.assertEqual(initialized.serverInfo.name, "NEXUS9")
                        tools = (await client.list_tools()).tools
                        self.assertEqual({t.name for t in tools}, {"nexus_catalog", "nexus_query", "nexus_manage"})
                        catalog = await call(client, "nexus_catalog", {})
                        self.assertEqual(len(catalog["heads"]), 9)
                        schema = await call(client, "nexus_catalog", {"operation": "context"})
                        self.assertFalse(schema["writes_project_code"])
                        for operation in ("investigation_save", "investigation", "runtime_status", "domain_pack"):
                            discovered = await call(client, "nexus_catalog", {"operation": operation})
                            self.assertFalse(discovered["schema"]["additionalProperties"])
                        await call(client, "nexus_manage", {"operation": "session_open", "parameters": {"name": "gps"}})
                        packet = await call(client, "nexus_query", {"operation": "context", "session": "gps", "parameters": {
                            "task": "Fix startGPS", "paths": ["gps.ts"], "constraints": ["Keep Expo 52"], "focus_symbols": {"gps.ts": "startGPS"}}})
                        self.assertIn("Keep Expo 52", packet["constraints"])
                        self.assertTrue(packet["items"])
                        await call(client, "nexus_manage", {"operation": "investigation_save", "parameters": {
                            "name": "gps_case", "body": {"objective": "Understand GPS behavior",
                                "hypotheses": [{"id": "h", "statement": "GPS returns 1"}],
                                "evidence": [{"id": "e", "summary": "Source observation", "hypothesis_ids": ["h"],
                                    "result": "supports", "files": ["gps.ts"]}],
                                "conclusions": [{"id": "c", "statement": "Source supports hypothesis", "evidence_ids": ["e"], "hypothesis_ids": ["h"]}],
                                "criteria": [{"id": "a", "requirement": "Inspect current source", "conclusion_ids": ["c"]}]}}})
                        explained = await call(client, "nexus_query", {"operation": "investigation", "parameters": {
                            "name": "gps_case", "conclusion_id": "c"}})
                        self.assertEqual(explained["status"], "supported_by_current_evidence")
                        status = await call(client, "nexus_query", {"operation": "runtime_status"})
                        self.assertEqual(status["version"], "0.4.0")
                        self.assertEqual(status["last_context_delivery"]["operation"], "context")
                        default_runner = await client.call_tool("nexus_manage", {"operation": "check_run",
                            "parameters": {"profile": "regression"}})
                        self.assertTrue(default_runner.isError)
                        await call(client, "nexus_manage", {"operation": "remember_read", "session": "gps", "parameters": {"path": "gps.ts"}})
                        (root / "gps.ts").write_text("export function startGPS() { return 2; }\n")
                        delta = await call(client, "nexus_query", {"operation": "delta", "session": "gps", "parameters": {"path": "gps.ts"}})
                        self.assertFalse(delta["unchanged"])
                        stale = await call(client, "nexus_query", {"operation": "investigation", "parameters": {"name": "gps_case"}})
                        self.assertTrue(stale["revalidation_required"])
                        bad = await client.call_tool("nexus_query", {"operation": "snippet", "parameters": {"path": "../outside.ts"}})
                        self.assertTrue(bad.isError)
                        unknown = await client.call_tool("nexus_query", {"operation": "unknown"})
                        self.assertTrue(unknown.isError)
                        await client.send_ping()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "project"
            root.mkdir()
            (root / "gps.ts").write_text("export function startGPS() { return 1; }\n")
            anyio.run(scenario, root, Path(temp) / "state")
