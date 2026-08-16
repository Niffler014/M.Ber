# Development Log: P1-01 Basic LangGraph Agent

## 1. Meta Information

- **Date:** 2026-08-16
- **Phase:** Phase 1 — Basic LangGraph Agent
- **Task ID:** P1-01
- **Task Title:** LangGraph State Graph, Nodes, Router & Observable CLI (基礎狀態圖、工作節點、路由器與可觀測 CLI)
- **Status:** COMPLETED

---

## 2. Goal

完成 JARVIS 專案 Phase 1 核心目標：
1. 定義型別安全的 `AgentState`，具備 `add_messages` 訊息累加機制。
2. 實作包含 `agent` 節點與 `tools` 節點的 `StateGraph`。
3. 建立 `should_continue` 條件邊（Conditional Edge / Router），根據 `tool_calls` 自動分流。
4. 提供 CLI 互動進入點 `app.cli`，即時觀察節點轉換與 State 變化。
5. 建立完整單元測試，驗證狀態圖編譯、對話流程、工具循環與 LLM 注入能力。

---

## 3. Why the Change Was Necessary

1. **從靜態結構進入動態 Agent Workflow**：Phase 0 僅完成環境與測試骨幹，Phase 1 建立了整個 JARVIS 的核心大腦引擎——LangGraph 狀態機。
2. **為 MCP / Tools 奠定循環骨幹**：現代 Agent 解決問題的本質是「思考 ➔ 調用工具 ➔ 獲取結果 ➔ 再次思考 ➔ 輸出」。透過本階段的 Graph 與 Router，我們成功把這個循環架構實作出來。
3. **無金鑰可測試性（Self-Contained）**：設計了兼具 LLM 注入與無 Key 模擬模式的架構，使專案即使在離線或無 API Key 時亦能完整執行所有自動化測試。

---

## 4. Files Changed

| File | Status | Description |
| :--- | :--- | :--- |
| `app/agent/state.py` | Created | 定義 `AgentState` 與訊息累加 Reducer |
| `app/agent/nodes.py` | Created | 實作 `agent_node`、`tools_node` 與 `dummy_tool` |
| `app/agent/graph.py` | Created | 建構 StateGraph、註冊 Nodes 與 Conditional Edge 路由 |
| `app/agent/__init__.py` | Created | 匯出 Agent 核心類別與函式 |
| `app/cli.py` | Created | CLI 終端互動介面，具備 State 轉換即時可觀測性 |
| `tests/test_agent_graph.py` | Created | 包含 6 個測試案例之完整單元測試 |
| `pyproject.toml` | Modified | 加入 `langgraph>=0.2.0` 依賴與 package 搜尋設定 |
| `CHANGELOG_AI.md` | Created | 遵循 Changelog Protocol 記錄 Phase 1 變更 |
| `docs/development-log/2026-08-16-p1-01-basic-langgraph-agent.md` | Created | 本次開發日誌 |

---

## 5. Detailed Explanation

### 5.1 `app/agent/state.py`
定義狀態字典：
```python
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
```
`add_messages` 確保每次節點回傳新訊息時，會以 append 的方式加入歷史，避免舊訊息遺失。

### 5.2 `app/agent/nodes.py`
- `create_agent_node(llm)`: 封裝 LLM 呼叫或無 Key 確定性模擬。如果使用者請求需要運算或查時，會發出 `AIMessage(..., tool_calls=[...])`。
- `tools_node(state)`: 解析最後一則訊息中的 `tool_calls`，執行工具並回傳 `ToolMessage`。

### 5.3 `app/agent/graph.py`
- `should_continue(state)`: 檢查最後訊息是否有 `tool_calls`。有則回傳 `"tools"`，無則回傳 `END`。
- `create_agent_graph(llm)`: 組裝 `StateGraph`，連接 `START -> agent -> (should_continue) -> tools / END` 以及 `tools -> agent`。

---

## 6. Before / After Architecture

### Before (Phase 0):
```text
[User] ──(無 Graph 運作機制)──> (僅有空模組)
```

### After (Phase 1):
```text
                          [START]
                             │
                             ▼
                      ┌─────────────┐
                      │    agent    │ ◄──────────┐
                      └──────┬──────┘            │
                             │                   │
                             ▼                   │
                     /───────────────\           │
                    < should_continue >          │
                     \───────────────/           │
                       │           │             │
        (無 tool_calls)│           │(有 tool_calls)
                       ▼           ▼             │
                    [ END ]     ┌─────────────┐  │
                                │    tools    │ ──┘
                                └─────────────┘
```

---

## 7. Important Code Concepts (新手重要概念)

1. **什麼是 Reducer？**
   - Reducer（歸納器/合併器）是狀態管理中的一種模式。它定義了「當舊資料遇到新資料時，該如何融合」。
   - `add_messages` 就是專門用來將新訊息附加至對話列表末端的 Reducer。
2. **什麼是 Tool Call 與 Tool Message？**
   - 當 LLM 決定呼叫工具時，它不會直接去執行程式，而是輸出一個「呼叫結構」（包含工具名稱與參數），這叫 `tool_calls`。
   - 外部程式（`tools_node`）執行完後，將結果包裝成 `ToolMessage`，帶有對應的 `tool_call_id`，再傳回給 LLM 閱讀。

---

## 8. Test Results

執行命令：
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

tests/test_agent_graph.py::test_graph_compilation PASSED                 [  7%]
tests/test_agent_graph.py::test_router_should_continue PASSED            [ 15%]
tests/test_agent_graph.py::test_normal_chat_execution_flow PASSED        [ 23%]
tests/test_agent_graph.py::test_tool_calling_execution_flow PASSED       [ 30%]
tests/test_agent_graph.py::test_dummy_tool_implementations PASSED        [ 38%]
tests/test_agent_graph.py::test_custom_mock_llm_injection PASSED         [ 46%]
tests/test_smoke.py::test_python_version PASSED                          [ 53%]
tests/test_smoke.py::test_core_dependencies_import PASSED                [ 61%]
tests/test_smoke.py::test_app_package_import PASSED                      [ 69%]
tests/test_smoke.py::test_project_spec_exists PASSED                     [ 76%]
tests/test_smoke.py::test_agents_rule_exists PASSED                      [ 84%]
tests/test_smoke.py::test_readme_exists PASSED                           [ 92%]
tests/test_smoke.py::test_pyproject_toml_exists PASSED                   [100%]

============================= 13 passed in 2.85s ==============================
```
**結果：13/13 測試全數通過（Passed）。**

---

## 9. Beginner Explanation (完全新手解析)

> 🤖 **打工人的工作日誌**：
> 
> - **Agent 節點** 就像公司的「經理」：他看過所有的對話（`messages`），決定現在要做什麼。如果客人只是打招呼，經理親自回覆（直接走到 `END`）。如果客人要查複雜的帳目或算公式，經理寫一張便條紙交代工項（`tool_calls`）。
> - **Router（should_continue）** 就像「秘書」：檢查經理有沒有寫便條紙。有便條紙就送去工程部（`tools` 節點），沒有就直接回信給客人（`END`）。
> - **Tools 節點** 就像「工程部」：看到便條紙上的要求，跑去按計算機或查時間，查完後把結果寫成報告（`ToolMessage`），送回給經理（回到 `agent` 節點）。
> - 經理看到工程部的報告後，用禮貌的話術統整成最後的回覆送出！

---

## 10. Next Step

- **Phase 2 — Own MCP Server**：
  - 建立專案自有的 MCP Server。
  - 將 Dummy Tools 遷移至標準 MCP Protocol 協定架構。
