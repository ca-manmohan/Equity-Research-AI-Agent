"""Stdio Model Context Protocol (MCP) Server for the Indian Investor Research Suite.

Exposes Stage 0 Investor Goals, KDB-X Multibagger Scanning, Indian Peer Comps,
Screener.in Free Fetch/Excel Parsing, Quarterly Earnings Review, Forensic Audit,
and Research Memo tools over standard JSON-RPC 2.0 stdio.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict

from agent_tools import OPENAI_TOOL_SCHEMAS, AgentWorkspace

SERVER_INFO = {
    "name": "indian-investor-mcp",
    "version": "1.0.0",
}


def _mcp_tools() -> list[Dict[str, Any]]:
    """Convert OpenAI function schemas into MCP tool definitions."""
    tools = []
    for entry in OPENAI_TOOL_SCHEMAS:
        fn = entry["function"]
        tools.append(
            {
                "name": fn["name"],
                "description": fn["description"],
                "inputSchema": fn["parameters"],
            }
        )
    return tools


def handle_request(ws: AgentWorkspace, req: Dict[str, Any]) -> Dict[str, Any] | None:
    """Process a single JSON-RPC 2.0 MCP request."""
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params") or {}

    if method == "notifications/initialized":
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": _mcp_tools()},
        }

    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments") or {}
        try:
            out_json = ws.dispatch(name, json.dumps(args))
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": out_json}],
                    "isError": False,
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"error": str(exc)})}],
                    "isError": True,
                },
            }

    if req_id is None:
        return None

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> None:
    ws = AgentWorkspace()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle_request(ws, req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
