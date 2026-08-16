# Development Log: P3-01 Third-party MCP Integration & MCP Manager

## 1. Meta Information

- **Date:** 2026-08-16
- **Phase:** Phase 3 — Third-party MCP Integration
- **Task ID:** P3-01
- **Task Title:** MCP Manager, External Config, SQLite Third-party Server & Safety Audit (MCP 總管、外部設定檔、SQLite 第三方伺服器與安全稽核)
- **Status:** COMPLETED

---

## 2. Goal

為 JARVIS 專案實作 Phase 3 核心目標：
1. 建立外部 JSON 設定檔 [`config/mcp_servers.json`](file:///e:/code/ive/M.Ber/config/mcp_servers.json)，集中管理所有 MCP 伺服器的啟動指令與狀態。
2. 實作 [`app/mcp/manager.py`](file:///e:/code/ive/M.Ber/app/mcp/manager.py) 中的 `MCPManager` 類別，負責多 Server 子程序連線池、工具清單探索（Tool Discovery）與智慧請求路由（Routing）。
3. 建立第三方風格的 SQLite 資料庫 MCP Server [`mcp_server/third_party/sqlite_server.py`](file:///e:/code/ive/M.Ber/mcp_server/third_party/sqlite_server.py)（提供 `read_notes` 與 `add_note` 工具）。
4. 實作安全權限模型（Safety & Permission Boundary），自動區分唯讀操作（READ_ONLY）與寫入修改操作（WRITE / MUTATION）並記錄稽核日誌。
5. 將 `MCPManager` 與 Phase 1 的 LangGraph Agent 及 CLI 介面完整對接，並通過 24/24 全套測試。

---

## 3. Why the Change Was Necessary

1. **從單一伺服器走向多伺服器架構**：Phase 2 僅能連接單一 Server，真實個人助理必須能同時掛載資料庫、日曆、檔案等多個獨立伺服器。
2. **外部設定檔驅動（Configuration-driven）**：讓未來新增或停用 MCP Server 時不需要修改 Python 程式碼，直接在 JSON 設定即可。
3. **落實安全防護規範**：依據 `AGENTS.md` 第 19 條與 `PROJECT_SPEC.md` 第 6 節，任何具外部副作用的操作（如寫入資料庫）必須具備明確的權限邊界與記錄。

---

## 4. Files Changed

| File | Status | Description |
| :--- | :--- | :--- |
| `config/mcp_servers.json` | Created | 外部 MCP 伺服器啟動與參數設定檔 |
| `mcp_server/third_party/sqlite_server.py` | Created | 第三方風格 SQLite 筆記與資料查詢 MCP Server |
| `mcp_server/third_party/__init__.py` | Created | 第三方伺服器套件初始化 |
| `app/mcp/manager.py` | Created | `MCPManager` 多伺服器總管模組（連線池、路由、安全稽核） |
| `app/mcp/__init__.py` | Modified | 匯出 `MCPManager` |
| `app/agent/nodes.py` | Modified | `tools_node` 與 `agent_node` 支援 MCP Manager 路由與筆記意圖 |
| `app/agent/graph.py` | Modified | `create_agent_graph` 支援注入 `mcp_manager` |
| `app/cli.py` | Modified | CLI 啟動時自動掛載所有設定之 MCP Servers |
| `tests/test_mcp_manager.py` | Created | MCP Manager 單元測試 |
| `tests/test_mcp_third_party.py` | Created | 第三方 SQLite MCP 伺服器與 Agent 整合測試 |
| `tests/test_mcp_integration.py` | Modified | 更新斷言與相容性 |
| `CHANGELOG_AI.md` | Modified | 記錄 Phase 3 變更與七大要素說明 |
| `docs/development-log/2026-08-16-p3-01-third-party-mcp-manager.md` | Created | 本次開發日誌 |

---

## 5. Detailed Explanation

### 5.1 `app/mcp/manager.py`
`MCPManager` 的核心架構：
```python
class MCPManager:
    def __init__(self, config_path=None):
        self.clients = {}      # server_name -> MCPStdioClient
        self.tool_routes = {}  # tool_name -> server_name
        self.reload_servers()

    def call_tool(self, tool_name, arguments):
        safety = self.evaluate_safety_level(tool_name, arguments)
        server_name = self.tool_routes.get(tool_name)
        return self.clients[server_name].call_tool(tool_name, arguments)
```

### 5.2 安全權限評估 (Safety Audit)
```python
def evaluate_safety_level(self, tool_name: str, arguments: Dict[str, Any]) -> str:
    mutation_prefixes = ["add_", "create_", "delete_", "update_", "write_", "modify_", "remove_", "insert_", "send_"]
    if any(tool_name.lower().startswith(p) for p in mutation_prefixes):
        return "WRITE / MUTATION"
    return "READ_ONLY"
```

---

## 6. Before / After Architecture

### Before (Phase 2):
```text
[LangGraph Agent] ──> [MCP Client (單一直連)] ──> [my_mcp_server.py]
```

### After (Phase 3):
```text
[config/mcp_servers.json]
         │ (讀取設定)
         ▼
 ┌───────────────┐
 │  MCP Manager  │ ◄──── [LangGraph Agent]
 └───────┬───────┘
         ├───────────────┬───────────────┐
         ▼ (stdio)       ▼ (stdio)       ▼ (stdio)
 ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
 │ own_server    │ │ sqlite_server │ │ (未來第三方)  │
 │ (時間/Echo)   │ │ (筆記資料庫)  │ │ (Google/Git)  │
 └───────────────┘ └───────────────┘ └───────────────┘
```

---

## 7. Test Results

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

tests/test_agent_graph.py::test_graph_compilation PASSED                 [  4%]
tests/test_agent_graph.py::test_router_should_continue PASSED            [  8%]
tests/test_agent_graph.py::test_normal_chat_execution_flow PASSED        [ 12%]
tests/test_agent_graph.py::test_tool_calling_execution_flow PASSED       [ 16%]
tests/test_agent_graph.py::test_dummy_tool_implementations PASSED        [ 20%]
tests/test_agent_graph.py::test_custom_mock_llm_injection PASSED         [ 25%]
tests/test_mcp_integration.py::test_agent_graph_with_mcp_get_current_time PASSED [ 29%]
tests/test_mcp_integration.py::test_agent_graph_with_mcp_echo_message PASSED [ 33%]
tests/test_mcp_manager.py::test_mcp_manager_initialization_and_tool_discovery PASSED [ 37%]
tests/test_mcp_manager.py::test_mcp_manager_multi_server_routing PASSED  [ 41%]
tests/test_mcp_manager.py::test_mcp_manager_safety_level_evaluation PASSED [ 45%]
tests/test_mcp_server.py::test_mcp_server_list_tools PASSED              [ 50%]
tests/test_mcp_server.py::test_mcp_server_call_get_current_time PASSED   [ 54%]
tests/test_mcp_server.py::test_mcp_server_call_echo_message PASSED       [ 58%]
tests/test_mcp_third_party.py::test_sqlite_server_add_and_read_notes_flow PASSED [ 62%]
tests/test_mcp_third_party.py::test_agent_graph_with_third_party_add_note PASSED [ 66%]
tests/test_mcp_third_party.py::test_agent_graph_with_third_party_read_notes PASSED [ 70%]
tests/test_smoke.py::test_python_version PASSED                          [ 75%]
tests/test_smoke.py::test_core_dependencies_import PASSED                [ 79%]
tests/test_smoke.py::test_app_package_import PASSED                      [ 83%]
tests/test_smoke.py::test_project_spec_exists PASSED                     [ 87%]
tests/test_smoke.py::test_agents_rule_exists PASSED                      [ 91%]
tests/test_smoke.py::test_readme_exists PASSED                           [ 95%]
tests/test_smoke.py::test_pyproject_toml_exists PASSED                   [100%]

============================= 24 passed in 42.55s =============================
```
**結果：24/24 測試全數通過（Passed）。**

---

## 8. Beginner Explanation (新手白話解析)

> 🏢 **總管辦公室與分機號碼**：
> 
> 現在的 JARVIS 大腦就像一間「公司總經理」：
> 1. 大腦不需要知道時間工具在哪個資料夾、筆記資料庫又在哪個硬碟。
> 2. 大腦只要跟「總管（`MCPManager`）」說：「我要寫入筆記」。
> 3. 總管翻開通訊錄（`mcp_servers.json`），自動撥通 SQLite 部門的分機號碼，把事情辦好後將結果回傳給大腦！
> 
> 任何時候你想讓公司多一個「天氣部門」或「發信部門」，只要在通訊錄上加一行，總管就會自動幫大腦接通新部門！

---

## 9. Next Step

- **Phase 4 — Calendar Integration**：
  - 實作個人行程管理與 Google / Local Calendar MCP 模組。
