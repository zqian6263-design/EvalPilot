# MCP error-propagation retrospective

This adapter evaluates the public `modelcontextprotocol/python-sdk` tool-error
boundary. It never imports both releases into one interpreter. The HTTP adapter
starts one probe subprocess with the Python executable from the selected pinned
virtual environment.

- public issue: https://github.com/modelcontextprotocol/python-sdk/issues/2770
- baseline: `mcp==2.2.0`
- candidate: `mcp==1.30.0`
- intervention: `mcp_v2_error_path_enabled`
- probe: `probe.py`
- HTTP contract: `server.py`
- workload: `workload.json`

The probe starts a real MCP stdio server, calls a real MCP client, and records
the observed result. It does not synthesize the observed channel, error code, or
data payload.

Run the full retrospective from the repository root:

```powershell
pwsh -NoProfile -File .\scripts\p4-mcp-retro-check.ps1
```
