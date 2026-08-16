# CHANGELOG_AI — JARVIS 專案變更紀錄

此文件遵循 AI 自動變更紀錄協議（Changelog Protocol），由 AI 助理在每次完成階段性里程碑並驗證通過後自動維護與更新。

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
> 想像我們今天在 JARVIS 體內蓋了一座「自動化智能作業流水線」：
> 1. **`AgentState`（工廠白板）**：所有工人共同記錄資訊的地方。當有新話語或新工具結果時，只會往下寫，絕不擦掉前面的紀錄。
> 2. **`agent` 節點（總指揮官大腦）**：負責看著白板上的對話歷史進行思考。如果使用者問的是簡單問題，指揮官直接寫下回答就出貨（結束）；如果使用者要計算數學或查時間，指揮官就在白板上貼一張「派工單（`tool_calls`）」。
> 3. **`should_continue`（紅綠燈分流器）**：檢查白板上有沒有派工單。有派工單就導向工具間，沒有就直接送出給使用者。
> 4. **`tools` 節點（工具維修手臂）**：看到派工單後拿出對應工具（如計算機），算完後把答案貼回白板，並把傳送帶轉回給總指揮官，由指揮官做最後的統整答覆。
> 
> 這套循環就是全世界所有高階 AI Agent（如 Claude Computer Use, ChatGPT Tools, AutoGen）最核心的底層運作模型！
