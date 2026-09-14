# P4 公开 MCP 回顾性诊断

Date: 2026-09-14

## Goal

Validate EvalPilot on a third public open-source path without changing the
core evaluator: a real MCP client/server SDK whose protocol-error behavior
changed between published major versions.

## Public source

- repository: https://github.com/modelcontextprotocol/python-sdk
- issue: https://github.com/modelcontextprotocol/python-sdk/issues/2770
- baseline: `mcp==2.2.0`
- candidate: `mcp==1.30.0`
- intervention: `mcp_v2_error_path_enabled`

The issue documents that the v1 decorator-based low-level server converts an
`McpError` raised by a tool handler into `CallToolResult(isError=true)`. The v2
API re-raises `MCPError`, so the client receives a JSON-RPC error with the
original structured code and data. This project evaluates that public behavior
as an observable version regression; it does not claim that all v1 deployments
are unsafe or that the v1 maintenance branch will receive a backport.

## Isolated execution

`integrations/mcp_retro/server.py` is an HTTP SUT adapter. It never imports the
MCP package into the EvalPilot process. Each request runs
`integrations/mcp_retro/probe.py` under one of two pinned virtual environments:

- `requirements-v1.txt`: `mcp==1.30.0`
- `requirements-v2.txt`: `mcp==2.2.0`

The probe starts a real MCP stdio server and a real MCP client, invokes a tool,
and records only the observed result. EvalPilot receives the observation through
the normal external-SUT contract and persists the request/response trace.

## Measured behavior

| Scenario | `mcp==2.2.0` | `mcp==1.30.0` |
|---|---|---|
| protocol error channel | `channel=jsonrpc_error` | `channel=call_tool_result` |
| structured error code | `structured_code=-32000` | `structured_code=none` |
| structured error data | `data_preserved=true` | `data_preserved=false` |
| successful tool call | result, `is_error=false` | result, `is_error=false` |
| ordinary Python exception | result, `is_error=true` | result, `is_error=true` |
| tools/list discovery | tool listed | tool listed |

## End-to-end result

The public workload contains three protocol observations and three controls.
EvalPilot found all three regressions, left all three controls stable, persisted
12 SUT traces, and confirmed every root cause with the executable v2 error-path
intervention. The release decision is `BLOCK / CRITICAL`.

See `docs/P4_MCP_RESULT.json` for run ids, scores, confidence interval, and
counterfactual results.

## Reproduce

```powershell
pwsh -NoProfile -File .\scripts\p4-mcp-retro-check.ps1
```

The command creates the pinned MCP environments under `.runtime`, starts the
HTTP adapter, evaluates both releases, runs the investigation, and performs the
counterfactual replay. Missing dependencies or probe failures fail the command
loudly; there is no mock fallback.
