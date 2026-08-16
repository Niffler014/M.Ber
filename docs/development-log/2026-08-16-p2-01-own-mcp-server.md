# Development Log: P2-01 Own MCP Server & Integration

## 1. Meta Information

- **Date:** 2026-08-16
- **Phase:** Phase 2 — Own MCP Server
- **Task ID:** P2-01
- **Task Title:** Own MCP Server, stdio Transport, MCP Client & LangGraph Integration (自有 MCP 伺服器、stdio 傳輸、MCP 客戶端與 LangGraph 整合)
- **Status:** COMPLETED

---

## 2. Goal

為 JARVIS 專案實作 Phase 2 核心目標：
1. 使用官方 Python MCP SDK 2.0.0 實作獨立的 MCP 伺服器 [`mcp_server/my_mcp_server.py`](file:///e:/code/ive/M.Ber/mcp_server/my_mcp_server.py)。
2. 在 MCP Server 中註冊低風險、無副作用工具：`get_current_time`（取得系統時間）與 `echo_message`（訊息回傳）。
3. 實作基於 `stdio` 傳輸的 [`app/mcp/client.py`](file:///e:/code/ive/M.Ber/app/mcp/client.py) 客戶端連接器。
4. 將 MCP Client 完整對接至 Phase 1 的 LangGraph Agent 與 CLI 介面。
5. 建立完整的單元測試與跨程序 stdio 整合測試。

---

## 3. Why the Change Was Necessary

1. **落實 Protocol-First 與模組解耦架構**：依據 `PROJECT_SPEC.md` 與 `AGENTS.md`，工具不應寫死在 Agent 程式內部，而應透過標準協定（MCP）對外連接。
2. **具備自製與自給自足能力**：JARVIS 不僅要能連接外部現成的 MCP Server，也需要具備自行擴充自定義 MCP Server 的能力。
3. **驗證 stdio 傳輸穩定性**：透過本機子程序管道通訊（stdio），免除開啟網路 Port 的安全隱患與跨機器設定成本。

---

## 4. Files Changed

| File | Status | Description |
| :--- | :--- | :--- |
| `mcp_server/my_mcp_server.py` | Created | 基於 `MCPServer` 與 stdio 的獨立 MCP 工具伺服器 |
| `mcp_server/__init__.py` | Created | 伺服器套件初始化與介面匯出 |
| `app/mcp/client.py` | Created | `MCPStdioClient` 客戶端連接器（支援 list_tools / call_tool） |
| `app/mcp/__init__.py` | Created | 客戶端套件初始化 |
| `app/agent/nodes.py` | Modified | `tools_node` 整合真實 MCP Client 調用 |
| `app/agent/graph.py` | Modified | `create_agent_graph` 支援注入 `mcp_client` |
| `app/cli.py` | Modified | CLI 啟動時自動探索並連接 MCP Server 工具 |
| `tests/test_mcp_server.py` | Created | MCP Server stdio 通訊與工具執行單元測試 |
| `tests/test_mcp_integration.py` | Created | LangGraph Agent 與 MCP Server 端到端整合測試 |
| `docs/architecture/protocol-versions.md` | Modified | 記錄 MCP SDK 2.0.0 與 stdio 規格 |
| `CHANGELOG_AI.md` | Modified | 記錄 Phase 2 變更與七大要素說明 |
| `docs/development-log/2026-08-16-p2-01-own-mcp-server.md` | Created | 本次開發日誌 |

---

## 5. Detailed Explanation

### 5.1 `mcp_server/my_mcp_server.py`
使用 MCP 2.0.0 的 `MCPServer`：
```python
app = MCPServer("jarvis-own-mcp-server")

@app.tool()
def get_current_time() -> str:
    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"[JARVIS MCP Time Tool]: 目前系統時間為 {current_time_str}"

@app.tool()
def echo_message(message: str) -> str:
    return f"[JARVIS MCP Echo Tool]: 收到回傳請求 -> '{message}'"
```

### 5.2 `app/mcp/client.py`
透過 `mcp.client.stdio.stdio_client` 建立連線：
```python
async with stdio_client(self._server_params) as (read_stream, write_stream):
    async with ClientSession(read_stream, write_stream) as session:
        await session.initialize()
        result = await session.call_tool(name, arguments)
```

---

## 6. Before / After Architecture

### Before (Phase 1):
```text
[Agent Node] ──(呼叫)──> [Tools Node] ──(執行寫死的 dummy Python 函式)
```

### After (Phase 2):
```text
[Agent Node] ──(產生 tool_calls)──> [Tools Node]
                                         │
                                         ▼ (stdio JSON-RPC 2.0)
                              ┌──────────────────────┐
                              │ mcp_server/          │
                              │   my_mcp_server.py   │
                              │ (獨立子程序運行)     │
                              └──────────────────────┘
```

---

## 7. Important Code Concepts (新手重要概念)

1. **什麼是 stdio（標準 I/O 通訊）？**
   - 就像在終端機裡面，你在鍵盤打字（stdin），螢幕印出字（stdout）。
   - 主程式和 MCP Server 之間使用同樣的方式，一問一答傳遞 JSON 資料，不需要透過網際網路。
2. **如何新增下一個自定義工具？（新手擴充指南）**
   - 只要在 [`mcp_server/my_mcp_server.py`](file:///e:/code/ive/M.Ber/mcp_server/my_mcp_server.py) 加上 `@app.tool()` 裝飾器，並寫好函式與型別標註，MCP Server 就會自動發佈給所有 Agent 使用！

---

## 8. Test Results

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

tests/test_agent_graph.py::test_graph_compilation PASSED                 [  5%]
tests/test_agent_graph.py::test_router_should_continue PASSED            [ 11%]
tests/test_agent_graph.py::test_normal_chat_execution_flow PASSED        [ 16%]
tests/test_agent_graph.py::test_tool_calling_execution_flow PASSED       [ 22%]
tests/test_agent_graph.py::test_dummy_tool_implementations PASSED        [ 27%]
tests/test_agent_graph.py::test_custom_mock_llm_injection PASSED         [ 33%]
tests/test_mcp_integration.py::test_agent_graph_with_mcp_get_current_time PASSED [ 38%]
tests/test_mcp_integration.py::test_agent_graph_with_mcp_echo_message PASSED [ 44%]
tests/test_mcp_server.py::test_mcp_server_list_tools PASSED              [ 50%]
tests/test_mcp_server.py::test_mcp_server_call_get_current_time PASSED   [ 55%]
tests/test_mcp_server.py::test_mcp_server_call_echo_message PASSED       [ 61%]
tests/test_smoke.py::test_python_version PASSED                          [ 66%]
tests/test_smoke.py::test_core_dependencies_import PASSED                [ 72%]
tests/test_smoke.py::test_app_package_import PASSED                      [ 77%]
tests/test_smoke.py::test_project_spec_exists PASSED                     [ 83%]
tests/test_smoke.py::test_agents_rule_exists PASSED                      [ 88%]
tests/test_smoke.py::test_readme_exists PASSED                           [ 94%]
tests/test_smoke.py::test_pyproject_toml_exists PASSED                   [100%]

============================= 18 passed in 9.90s ==============================
```
**結果：18/18 測試全數通過（Passed）。**

---

## 9. Beginner Explanation (新手白話解析)

> 🔌 **從「專用接頭」到「通用 Type-C 插座」**：
> 
> 在 Phase 1，我們的工具像是一顆「焊死在電路板上的電池」。
> 在 Phase 2，我們做了一個標準的「Type-C 插座（`app/mcp/client.py`）」和一顆「Type-C 充電寶（`my_mcp_server.py`）」。
> 大腦想要電（要時間、要 echo）時，插上 Type-C 線就能通電。
> 未來如果我們想接別人的充電寶（第三方 MCP Server，如日曆、資料庫），只要把同一條線插過去即可！

---

## 10. Next Step

- **Phase 3 — Third-party MCP Integration**：
  - 載入外部社群現成 MCP Server（例如檔案管理 MCP 或 SQLite MCP）。
  - 實作多 MCP Server 管理器（MCP Manager）。
