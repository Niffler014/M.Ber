# Protocol Versions

This document records the protocol and SDK versions used by JARVIS.

The purpose of this document is to prevent AI coding agents from silently implementing an outdated tutorial or specification.

---

## MCP

### Current Project Status

MCP integration has not yet been implemented.

### Reference

The implementation must consult the official MCP specification before Phase 2.

Official specification:

https://modelcontextprotocol.io/specification/

### Required Record

When MCP implementation begins, record:

- MCP specification version
- MCP SDK
- SDK version
- Transport used
- Compatibility notes

---

## A2A

### Current Project Status

A2A integration has not yet been implemented.

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

LangGraph is the planned orchestration runtime.

The current implementation must record the installed package version.

Reference:

https://docs.langchain.com/oss/python/langgraph/

---

## LangChain

LangChain will provide model/tool/agent integrations where appropriate.

The current implementation must record the installed package version.

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