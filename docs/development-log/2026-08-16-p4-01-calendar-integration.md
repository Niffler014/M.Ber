# Development Log: P4-01 Calendar Integration & Timezone Context

## 1. Meta Information

- **Date:** 2026-08-16
- **Phase:** Phase 4 — Calendar Integration
- **Task ID:** P4-01
- **Task Title:** Calendar MCP Server, ISO 8601 Robust Parsing, Dynamic Timezone Context & High-risk Operation Guardrails
- **Status:** COMPLETED

---

## 2. Goal

為 JARVIS 建立專屬的 **Calendar MCP Server**，實作完整的行事曆行程管理功能：
1. 建立獨立的 Calendar MCP Server [`mcp_server/third_party/calendar_server.py`](file:///e:/code/ive/M.Ber/mcp_server/third_party/calendar_server.py)，提供 `query_events`、`add_event`、`update_event`、`delete_event` 四大標準工具。
2. 實作強韌容錯的時間剖析器 `parse_flexible_datetime`，支援 ISO 8601、空格分隔、斜線格式等。
3. 在 LangGraph Agent 節點中動態注入當前系統時間（`Current Time`）與時區（`Timezone`），使 LLM 能精準計算相對時間（例如「明天下午 3 點」）。
4. 在 MCP Manager 中實作高風險寫入/刪除操作的權限邊界攔截，記錄 `[PERMISSION REQUIRED: WRITE/DELETE]` 稽核日誌。
5. 建立完整的測試套件並通過 34/34 全套回歸測試。

---

## 3. Architecture & Data Flow

```text
[使用者輸入：「幫我預約明天下午 3 點開會」]
                       │
                       ▼
          ┌───────────────────────────┐
          │     LangGraph Agent       │ ◄── 注入時間錨點: (2026-08-16 21:05, Asia/Taipei)
          └────────────┬──────────────┘
                       │ (推算出 start_time='2026-08-17T15:00:00')
                       ▼
          ┌───────────────────────────┐
          │        MCP Manager        │ ──> 🚨 安全稽核: [PERMISSION REQUIRED: WRITE/DELETE]
          └────────────┬──────────────┘
                       │ (stdio JSON-RPC 路由)
                       ▼
          ┌───────────────────────────┐
          │    calendar_server.py     │ ──> 寫入 SQLite (data/calendar.db)
          └───────────────────────────┘
```

---

## 4. Files Changed

| File | Status | Description |
| :--- | :--- | :--- |
| `mcp_server/third_party/calendar_server.py` | Created | Calendar MCP Server（CRUD 行程工具與容錯時間解析） |
| `config/mcp_servers.json` | Modified | 註冊 `calendar_server` |
| `app/agent/nodes.py` | Modified | 動態注入時間/時區 Context，新增行程相對時間轉換 |
| `app/mcp/manager.py` | Modified | 強化多 Server 載入與高風險操作權限日誌 |
| `app/mcp/client.py` | Modified | 支援傳入自訂 command、args 與 env |
| `app/cli.py` | Modified | 新增行事曆測試關鍵字提示 |
| `tests/test_calendar_server.py` | Created | 行事曆 Server 單元測試 |
| `tests/test_calendar_integration.py` | Created | 行事曆 Agent 整合測試 |
| `CHANGELOG_AI.md` | Modified | 記錄 Phase 4 變更與七大要素說明 |
| `docs/development-log/2026-08-16-p4-01-calendar-integration.md` | Created | 本次開發日誌 |

---

## 5. Test Results

執行指令：
```powershell
uv run --extra dev pytest
```

輸出結果：
```text
============================= test session starts =============================
platform win32 -- Python 3.14.4, pytest-9.1.1, pluggy-1.6.0
rootdir: E:\code\ive\M.Ber
configfile: pyproject.toml
testpaths: tests

tests/test_agent_graph.py::test_graph_compilation PASSED                 [  2%]
tests/test_agent_graph.py::test_router_should_continue PASSED            [  5%]
tests/test_agent_graph.py::test_normal_chat_execution_flow PASSED        [  8%]
tests/test_agent_graph.py::test_tool_calling_execution_flow PASSED       [ 11%]
tests/test_agent_graph.py::test_dummy_tool_implementations PASSED        [ 14%]
tests/test_agent_graph.py::test_custom_mock_llm_injection PASSED         [ 17%]
tests/test_calendar_integration.py::test_mcp_manager_calendar_routing_and_safety PASSED [ 20%]
tests/test_calendar_integration.py::test_agent_graph_relative_time_calendar_add_event PASSED [ 23%]
tests/test_calendar_integration.py::test_agent_graph_calendar_query_events PASSED [ 26%]
tests/test_calendar_server.py::test_parse_flexible_datetime PASSED       [ 29%]
tests/test_calendar_server.py::test_calendar_crud_flow PASSED            [ 32%]
tests/test_line_gateway.py::test_line_gateway_health_check PASSED        [ 35%]
tests/test_line_gateway.py::test_line_gateway_missing_signature PASSED   [ 38%]
tests/test_line_gateway.py::test_line_gateway_invalid_signature PASSED   [ 41%]
tests/test_line_gateway.py::test_line_gateway_valid_webhook_event_processing PASSED [ 44%]
tests/test_line_gateway.py::test_line_gateway_multi_user_thread_isolation PASSED [ 47%]
tests/test_mcp_integration.py::test_agent_graph_with_mcp_get_current_time PASSED [ 50%]
tests/test_mcp_integration.py::test_agent_graph_with_mcp_echo_message PASSED [ 52%]
tests/test_mcp_manager.py::test_mcp_manager_initialization_and_tool_discovery PASSED [ 55%]
tests/test_mcp_manager.py::test_mcp_manager_multi_server_routing PASSED  [ 58%]
tests/test_mcp_manager.py::test_mcp_manager_safety_level_evaluation PASSED [ 61%]
tests/test_mcp_server.py::test_mcp_server_list_tools PASSED              [ 64%]
tests/test_mcp_server.py::test_mcp_server_call_get_current_time PASSED   [ 67%]
tests/test_mcp_server.py::test_mcp_server_call_echo_message PASSED       [ 70%]
tests/test_mcp_third_party.py::test_sqlite_server_add_and_read_notes_flow PASSED [ 73%]
tests/test_mcp_third_party.py::test_agent_graph_with_third_party_add_note PASSED [ 76%]
tests/test_mcp_third_party.py::test_agent_graph_with_third_party_read_notes PASSED [ 79%]
tests/test_smoke.py::test_python_version PASSED                          [ 82%]
tests/test_smoke.py::test_core_dependencies_import PASSED                [ 85%]
tests/test_smoke.py::test_app_package_import PASSED                      [ 88%]
tests/test_smoke.py::test_project_spec_exists PASSED                     [ 91%]
tests/test_smoke.py::test_agents_rule_exists PASSED                      [ 94%]
tests/test_smoke.py::test_readme_exists PASSED                           [ 97%]
tests/test_smoke.py::test_pyproject_toml_exists PASSED                   [100%]

======================== 34 passed in 82.98s (0:01:22) ========================
```
**結果：34/34 測試全數通過（Passed，100% 成功率）。**
