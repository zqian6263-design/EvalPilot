"""Measure MCP error propagation with the public SDK under an isolated venv."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from importlib.metadata import version
from typing import Any

MCP_DISTRIBUTION_VERSION = version("mcp")
MCP_MAJOR = int(MCP_DISTRIBUTION_VERSION.split(".", 1)[0])
PROTOCOL_CODE = -32000
PROTOCOL_DATA = {"probe": "preserve-protocol-error", "severity": "critical"}
SCENARIOS = {
    "protocol-error-channel",
    "protocol-error-code",
    "protocol-error-data",
    "tool-success-control",
    "ordinary-exception-control",
    "tool-discovery-control",
}


def build_server() -> Any:
    if MCP_MAJOR < 2:
        from mcp.server.fastmcp import FastMCP
        from mcp.shared.exceptions import ErrorData, McpError

        server = FastMCP("mcp-retro-probe-v1")

        @server.tool()
        def explode(value: str) -> str:
            if value == "protocol":
                raise McpError(
                    ErrorData(
                        code=PROTOCOL_CODE,
                        message="structured fault",
                        data=PROTOCOL_DATA,
                    )
                )
            if value == "ordinary":
                raise ValueError("ordinary tool failure")
            return f"ok:{value}"

        return server

    from mcp import MCPError
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("mcp-retro-probe-v2")

    @server.tool()
    def explode(value: str) -> str:
        if value == "protocol":
            raise MCPError(
                code=PROTOCOL_CODE,
                message="structured fault",
                data=PROTOCOL_DATA,
            )
        if value == "ordinary":
            raise ValueError("ordinary tool failure")
        return f"ok:{value}"

    return server


def _text(result: Any) -> str:
    parts: list[str] = []
    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)
        if text is not None:
            parts.append(str(text))
    return "\n".join(parts)


def _exception_observation(exc: Exception) -> dict[str, Any]:
    error = getattr(exc, "error", None)
    return {
        "kind": "exception",
        "exception_type": type(exc).__name__,
        "code": getattr(exc, "code", getattr(error, "code", None)),
        "data": getattr(exc, "data", getattr(error, "data", None)),
        "text": str(exc),
    }


def _result_observation(result: Any) -> dict[str, Any]:
    is_error = getattr(result, "isError", getattr(result, "is_error", None))
    return {
        "kind": "result",
        "is_error": bool(is_error),
        "text": _text(result),
    }


def _call_v1(value: str, list_only: bool = False) -> dict[str, Any]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def run() -> dict[str, Any]:
        params = StdioServerParameters(
            command=sys.executable,
            args=[__file__, "--server"],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                if list_only:
                    listed = await session.list_tools()
                    return {
                        "tools": [tool.name for tool in listed.tools],
                        "tool_calls": ["mcp.list_tools"],
                    }
                try:
                    result = await session.call_tool("explode", {"value": value})
                except Exception as exc:  # noqa: BLE001 - normalized as measured evidence.
                    observation = _exception_observation(exc)
                    observation["tool_calls"] = ["mcp.call_tool:explode"]
                    return observation
                observation = _result_observation(result)
                observation["tool_calls"] = ["mcp.call_tool:explode"]
                return observation

    return asyncio.run(run())


def _call_v2(value: str, list_only: bool = False) -> dict[str, Any]:
    from mcp import Client, StdioServerParameters

    async def run() -> dict[str, Any]:
        params = StdioServerParameters(
            command=sys.executable,
            args=[__file__, "--server"],
        )
        async with Client(params, raise_exceptions=True) as client:
            if list_only:
                listed = await client.list_tools()
                return {
                    "tools": [tool.name for tool in listed.tools],
                    "tool_calls": ["mcp.list_tools"],
                }
            try:
                result = await client.call_tool("explode", {"value": value})
            except Exception as exc:  # noqa: BLE001 - normalized as measured evidence.
                observation = _exception_observation(exc)
                observation["tool_calls"] = ["mcp.call_tool:explode"]
                return observation
            observation = _result_observation(result)
            observation["tool_calls"] = ["mcp.call_tool:explode"]
            return observation

    return asyncio.run(run())


def _invoke(value: str | None, *, list_only: bool = False) -> dict[str, Any]:
    if MCP_MAJOR < 2:
        return _call_v1(value or "", list_only=list_only)
    return _call_v2(value or "", list_only=list_only)


def observe(scenario_id: str, intervention: str | None) -> dict[str, Any]:
    del intervention  # The runtime version is selected by the HTTP adapter.
    if scenario_id not in SCENARIOS:
        raise ValueError(f"unknown MCP probe scenario: {scenario_id}")

    if scenario_id == "tool-discovery-control":
        observation = _invoke(None, list_only=True)
        listed = "explode" in observation["tools"]
        answer = f"runtime={MCP_DISTRIBUTION_VERSION}; tool_listed={str(listed).lower()}"
        tool_calls = observation["tool_calls"]
    else:
        value = "protocol" if scenario_id.startswith("protocol-") else (
            "ordinary" if scenario_id == "ordinary-exception-control" else "success"
        )
        observation = _invoke(value)
        tool_calls = observation["tool_calls"]
        if scenario_id == "protocol-error-channel":
            channel = (
                "jsonrpc_error"
                if observation["kind"] == "exception"
                else "call_tool_result"
            )
            answer = f"runtime={MCP_DISTRIBUTION_VERSION}; channel={channel}"
        elif scenario_id == "protocol-error-code":
            code = observation.get("code") if observation["kind"] == "exception" else None
            answer = (
                f"runtime={MCP_DISTRIBUTION_VERSION}; "
                f"structured_code={code if code is not None else 'none'}"
            )
        elif scenario_id == "protocol-error-data":
            data = observation.get("data") if observation["kind"] == "exception" else None
            preserved = isinstance(data, dict) and data.get("probe") == PROTOCOL_DATA["probe"]
            answer = (
                f"runtime={MCP_DISTRIBUTION_VERSION}; "
                f"data_preserved={str(preserved).lower()}"
            )
        elif scenario_id == "ordinary-exception-control":
            answer = (
                f"runtime={MCP_DISTRIBUTION_VERSION}; outcome={observation['kind']}; "
                f"is_error={str(observation.get('is_error')).lower()}"
            )
        else:
            answer = (
                f"runtime={MCP_DISTRIBUTION_VERSION}; outcome={observation['kind']}; "
                f"is_error={str(observation.get('is_error')).lower()}; "
                f"text={observation.get('text', '')}"
            )

    return {
        "answer": answer,
        "citations": [
            f"mcp-sdk:{MCP_DISTRIBUTION_VERSION}",
            "mcp-issue:2770",
        ],
        "tool_calls": tool_calls,
        "observation": observation,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario_id", nargs="?")
    parser.add_argument("--intervention", default="")
    parser.add_argument("--server", action="store_true")
    args = parser.parse_args()

    if args.server:
        build_server().run(transport="stdio")
        return 0
    if not args.scenario_id:
        parser.error("scenario_id is required unless --server is used")
    print(
        json.dumps(
            observe(args.scenario_id, args.intervention or None),
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
