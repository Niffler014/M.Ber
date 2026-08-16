# Protocol Versions

This document records the protocol and SDK versions used by JARVIS.

The purpose of this document is to prevent AI coding agents from silently implementing an outdated tutorial or specification.

---

## MCP

### Current Project Status

Phase 4 (Calendar Integration) completed. MCP is actively used across own server and third-party servers via `MCPManager`.

### Reference

Official specification:
https://modelcontextprotocol.io/specification/

### Recorded Configuration (Phase 4)

- **MCP Specification Version**: 2024-11-05 (Model Context Protocol Standard)
- **MCP SDK**: `mcp` (Python official SDK)
- **SDK Version**: `2.0.0`
- **Transport**: `stdio` (JSON-RPC 2.0 via sub-process standard I/O streams)
- **Active Servers (Managed via config/mcp_servers.json & MCPManager)**:
  - `own_server` (`mcp_server/my_mcp_server.py`):
    - Tools: `get_current_time`, `echo_message`
  - `sqlite_server` (`mcp_server/third_party/sqlite_server.py`):
    - Tools: `read_notes`, `add_note`
  - `calendar_server` (`mcp_server/third_party/calendar_server.py`):
    - Tools: `query_events`, `add_event`, `update_event`, `delete_event`
- **Compatibility Notes**:
  - Requires `anyio` for asynchronous standard I/O streams handling.
  - Subprocess execution supports cross-platform python invocation with PYTHONPATH configuration.
  - Local project package uses `mcp_server/` (not `mcp/`) to avoid Python namespace shadowing.

---

## A2A

### Current Project Status

A2A integration has not yet been implemented (Planned for Phase 6).

### Current Official Major Version

A2A 1.0.0

### Reference

https://a2a-protocol.org/latest/

### Required Record

When A2A implementation begins, record:

- A2A specification version
- A2A SDK
- SDK version
- Transport
- Agent Card format
- Authentication mechanism
- Compatibility notes

---

## LangGraph

### Current Project Status

Active orchestration runtime powering `app/agent/graph.py`, supporting StateGraph, conditional routing, checkpointer state isolation (MemorySaver), and dynamic tool binding.

Reference:

https://docs.langchain.com/oss/python/langgraph/

---

## LangChain

### Current Project Status

Active framework providing core messages (`HumanMessage`, `AIMessage`, `ToolMessage`), schema bindings, and abstraction layers.

Reference:

https://docs.langchain.com/oss/python/langchain/

---

## Version Policy

Protocol versions MUST NOT be changed silently.

If a protocol or SDK is upgraded:

1. Explain why.
2. Update this document.
3. Run relevant tests.
4. Create a Development Log.
5. Record compatibility changes.