"""Real stdio handshake and fail-closed policy smoke test before registration."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run(python, src):
    with tempfile.TemporaryDirectory(prefix="nexus9-smoke-") as temp:
        root = Path(temp) / "project"
        root.mkdir()
        (root / "example.py").write_text("def hello():\n    return 42\n", encoding="utf-8")
        params = StdioServerParameters(command=python, args=["-m", "nexus9.server", "--root", str(root),
            "--state-dir", str(Path(temp) / "state"), "--hardware", "light", "--memory-owner", "external",
            "--compression-owner", "external"], env={**os.environ, "PYTHONPATH": str(src), "PYTHONUTF8": "1"})
        with anyio.fail_after(30):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    names = {tool.name for tool in (await client.list_tools()).tools}
                    if names != {"nexus_catalog", "nexus_query", "nexus_manage"}:
                        raise ValueError("unexpected tool catalog")
                    response = await client.call_tool("nexus_query", {"operation": "health"})
                    if response.isError or json.loads(response.content[0].text)["state_integrity"] != "ok":
                        raise ValueError("health check failed")
                    blocked = await client.call_tool("nexus_manage", {"operation": "memory_save", "parameters": {
                        "body": {"goal": "smoke validation"}}})
                    if not blocked.isError or "runtime policy" not in blocked.content[0].text:
                        raise ValueError("external memory ownership was not enforced")
                    response = await client.call_tool("nexus_query", {"operation": "context", "parameters": {
                        "task": "Inspect hello", "paths": ["example.py"], "focus_symbols": {"example.py": "hello"}}})
                    if response.isError or not json.loads(response.content[0].text)["items"]:
                        raise ValueError("context check failed")
                    await client.send_ping()
    print("MCP smoke: handshake, 3 tools, health, light context and policy rejection passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-python", default=sys.executable)
    parser.add_argument("--src", default=str(Path(__file__).resolve().parents[1] / "src"))
    args = parser.parse_args()
    anyio.run(run, args.server_python, Path(args.src).resolve())
