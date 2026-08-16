# CHANGELOG_AI — JARVIS 專案變更紀錄

此文件遵循 AI 自動變更紀錄協議（Changelog Protocol），由 AI 助理在每次完成階段性里程碑並驗證通過後自動維護與更新。

---

## [Phase 2] 自有 MCP 伺服器與 Agent 對接 (Own MCP Server & Integration)

- **紀錄時間**：2026-08-16 19:38 (UTC+8)
- **修改類型**：[新增/升級] Phase 2: Own MCP Server (自有 MCP 伺服器)
- **涉及檔案**：
  - `mcp_server/my_mcp_server.py` (新增)
  - `mcp_server/__init__.py` (新增)
  - `app/mcp/client.py` (新增)
  - `app/mcp/__init__.py` (新增)
  - `app/agent/nodes.py` (修改)
  - `app/agent/graph.py` (修改)
  - `app/cli.py` (修改)
  - `tests/test_mcp_server.py` (新增)
  - `tests/test_mcp_integration.py` (新增)
  - `docs/architecture/protocol-versions.md` (修改)
  - `docs/development-log/2026-08-16-p2-01-own-mcp-server.md` (新增)
- **修改原因 / 邏輯**：
  - 將 Phase 1 的內嵌 Dummy Tools 升級為符合全球標準 Model Context Protocol (MCP) 的獨立伺服器架構。
  - 使用官方 Python MCP SDK 2.0.0 (`MCPServer`) 實作基於 `stdio` 傳輸的獨立伺服器，註冊 `get_current_time` 與 `echo_message` 工具。
  - 實作 `MCPStdioClient` 作為通訊連接器，在 LangGraph 執行時動態啟動 Server 子程序並發送 JSON-RPC 請求取得結果。
- **對整體架構影響**：
  - **模組完全解耦**：工具實作與 Agent 調度大腦徹底分開。JARVIS 不再依賴寫死在 Agent 內部的工具函式，而是能以標準 MCP 協定外接任何工具。
  - **為 Phase 3 (Third-party MCP) 鋪路**：目前的 `MCPStdioClient` 已具備通用性，後續要載入社群現成的 MCP Server（如 SQLite MCP、GitHub MCP、Brave Search MCP）只需傳入對應指令即可無縫掛載。
- **如何測試**：
  1. 單元測試：`uv run --extra dev pytest tests/test_mcp_server.py`（驗證 Server stdio 通訊與各工具執行）。
  2. 整合測試：`uv run --extra dev pytest tests/test_mcp_integration.py`（驗證 LangGraph + MCP 完整對話循環）。
  3. CLI 互動：`uv run python -m app.cli`（即時輸入「現在幾點」與「echo 測試」驗證動態呼叫）。
  4. 全套測試：`uv run --extra dev pytest`（18/18 測試全數通過）。

### Beginner Explanation (新手解釋：什麼是自己建立的 MCP Server？)

> 🧰 **「從工具箱裡拿工具」vs「連線到外部工具加工廠」**：
> 
> - **在 Phase 1**：我們把計算機函式直接寫死在 Agent 程式碼裡。這就像把板手直接焊死在機器人手臂上，如果要換工具就得拆機器人大腦。
> - **在 Phase 2（現在）**：我們把工具搬移到一個獨立的小房間（`my_mcp_server.py`），並在機器人與小房間之間插上一條標準傳輸線（`stdio` 管道）。
> - 當機器人需要查時間或回傳訊息時，機器人透過傳輸線發送訊息：「請幫我跑一下 `get_current_time` 工具」，小房間算好後透過傳輸線回傳結果。
> 
> 這樣的好處是：**工具房間愛怎麼改就怎麼改，甚至可以搬到別人電腦上跑，機器人大腦完全不受影響！** 這就是 MCP 協定強大的「解耦與通用性」！

---

## [Phase 1] 基礎 LangGraph 狀態圖代理人 (Basic LangGraph Agent)

- **紀錄時間**：2026-08-16 18:34 (UTC+8)
- **變更類型**：[新增] Phase 1: 基礎 LangGraph Agent
- **涉及檔案**：
  - `app/agent/state.py` (新增)
  - `app/agent/nodes.py` (新增)
  - `app/agent/graph.py` (新增)
  - `app/agent/__init__.py` (新增)
  - `app/cli.py` (新增)
  - `tests/test_agent_graph.py` (新增)
  - `pyproject.toml` (修改)
  - `docs/development-log/2026-08-16-p1-01-basic-langgraph-agent.md` (新增)
- **核心內容**：
  1. 定義 `AgentState` 資料結構，利用 `Annotated[Sequence[BaseMessage], add_messages]` 提供訊息累加 Reducer 機制。
  2. 建立 `agent` 大腦思考節點與 `tools` 工具調用節點（內含 Dummy Calculator, System Time, Echo 工具支援）。
  3. 實作 `should_continue` 條件路由（Conditional Edge），根據訊息中是否帶有 `tool_calls` 自動分流至工具節點或結束對話。
  4. 建立 `app.cli` 命令列互動進入點，支援即時 State 流轉視覺化監控。
  5. 建立完整 pytest 單元測試（13/13 測試全數通過）。
- **對後續 MCP 整合的影響評估**：
  - **極度有利 / 無縫銜接**：本次建立的 `tools_node` 與 `should_continue` 路由機制是現代 Agent Tool-Calling 的標準協定。在 Phase 2 (Own MCP Server) 與 Phase 3 (Third-party MCP) 實作時，核心 Graph 結構完全無需重構，只需將 `dummy_tool` 替換為標準的 MCP Client 工具呼叫介面即可。

### Beginner Explanation (新手解釋)

> 🏭 **現代化智能工廠與傳送帶的比喻**：
> 
> 想像我們在 JARVIS 體內蓋了一座「自動化智能作業流水線」：
> 1. `AgentState`：工廠白板。所有工人共同記錄資訊的地方。
> 2. `agent` 節點：總指揮官大腦。看著白板思考，需要工具時貼出派工單（`tool_calls`）。
> 3. `should_continue`：分流器。有派工單導向工具間，沒有就出貨（結束）。
> 4. `tools` 節點：工具維修手臂。執行派工單，回傳結果給指揮官做最後統整。
