# CHANGELOG_AI — JARVIS 專案變更紀錄

此文件遵循 AI 自動變更紀錄協議（Changelog Protocol），由 AI 助理在每次完成階段性里程碑並驗證通過後自動維護與更新。

---

## [Phase 3] 第三方 MCP 整合與 MCP Manager 總管模組 (Third-party MCP Integration)

- **紀錄時間**：2026-08-16 20:02 (UTC+8)
- **修改類型**：[新增/升級] Phase 3: Third-party MCP Integration (第三方 MCP 整合)
- **涉及檔案**：
  - `config/mcp_servers.json` (新增)
  - `mcp_server/third_party/sqlite_server.py` (新增)
  - `mcp_server/third_party/__init__.py` (新增)
  - `app/mcp/manager.py` (新增)
  - `app/mcp/__init__.py` (修改)
  - `app/agent/nodes.py` (修改)
  - `app/agent/graph.py` (修改)
  - `app/cli.py` (修改)
  - `tests/test_mcp_manager.py` (新增)
  - `tests/test_mcp_third_party.py` (新增)
  - `tests/test_mcp_integration.py` (修改)
  - `docs/development-log/2026-08-16-p3-01-third-party-mcp-manager.md` (新增)
- **修改原因 / 邏輯**：
  - 實作外部設定檔驅動架構（`config/mcp_servers.json`），免除程式碼寫死伺服器啟動指令。
  - 實作 `MCPManager` 多伺服器總管模組，管理多個 Server 連線池（Client Pool）、自動工具探索彙整（`list_all_tools`）、智慧請求路由（`call_tool`）與子程序生命週期。
  - 建立第三方風格的 SQLite 筆記與資料庫伺服器（`sqlite_server.py`），提供 `read_notes` 與 `add_note` 工具。
  - 實作安全權限模型（Safety & Permission Boundary），自動區分 `READ_ONLY` 與 `WRITE / MUTATION` 操作並記錄安全稽核日誌。
- **對整體架構影響**：
  - **具備無限擴充能力**：JARVIS 正式具備「動態掛載多個外部工具伺服器」的能力。未來要載入任何社群或第三方開源 MCP Server（如 GitHub、Google Drive、Notion），只需在 `mcp_servers.json` 加一行設定即可直接使用！
  - **確立安全稽核基礎**：寫入操作在執行前均有明確的攔截日誌標記，為後續 Phase 的人機協作（Human-in-the-Loop）審批打下基礎。
- **如何測試**：
  1. 總管單元測試：`uv run --extra dev pytest tests/test_mcp_manager.py`（測試設定檔載入、多 Server 連線、工具路由與安全評估）。
  2. 第三方整合測試：`uv run --extra dev pytest tests/test_mcp_third_party.py`（測試 SQLite 筆記讀寫與 Agent 端到端調用）。
  3. CLI 互動測試：`uv run python -m app.cli`（驗證同時掛載 own_server 與 sqlite_server）。
  4. 全套回歸測試：`uv run --extra dev pytest`（24/24 測試全數通過）。

### Beginner Explanation (新手解釋：JARVIS 是如何跟外部世界溝通的？)

> 🔌 **從「單孔充電器」升級成「智慧多孔 USB Hub（集線器）」**：
> 
> - **在 Phase 2**：我們的 JARVIS 只能連線到自己寫的一個小工具伺服器（就像手機只能插一條專用充電線）。
> - **在 Phase 3（現在）**：我們給 JARVIS 裝上了一個「智慧 USB 集線器（`MCPManager`）」和一張「外接設備清單（`mcp_servers.json`）」。
> - 清單上寫著：1 號孔插「自有工具箱（`my_mcp_server`）」、2 號孔插「SQLite 資料庫（`sqlite_server`）」。
> - 當你對 JARVIS 說「幫我記一下明天要買牛奶」，JARVIS 大腦發出 `add_note` 指令；集線器一秒看懂這是資料庫的工具，自動把請求送去 2 號孔執行，並在螢幕上留下【寫入操作安全記錄】。
> 
> 現在的 JARVIS 就像插上了全世界的通用外接卡，隨時可以連上任何第三方軟體！

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
- **核心內容**：
  1. 使用官方 Python MCP SDK 2.0.0 (`MCPServer`) 實作基於 `stdio` 傳輸的獨立伺服器，註冊 `get_current_time` 與 `echo_message` 工具。
  2. 實作 `MCPStdioClient` 作為通訊連接器，在 LangGraph 執行時動態啟動 Server 子程序並發送 JSON-RPC 請求取得結果。

---

## [Phase 1] 基礎 LangGraph 狀態圖代理人 (Basic LangGraph Agent)

- **紀錄時間**：2026-08-16 18:34 (UTC+8)
- **變更類型**：[新增] Phase 1: 基礎 LangGraph Agent
- **核心內容**：
  1. 定義 `AgentState` 資料結構與 `add_messages` Reducer 機制。
  2. 建立 `agent` 大腦思考節點與 `tools` 工具調用節點。
  3. 實作 `should_continue` 條件路由（Conditional Edge）。
  4. 建立 `app.cli` 命令列互動進入點與單元測試。
