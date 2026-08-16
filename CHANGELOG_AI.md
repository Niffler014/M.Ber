# CHANGELOG_AI — JARVIS 專案變更紀錄

此文件遵循 AI 自動變更紀錄協議（Changelog Protocol），由 AI 助理在每次完成階段性里程碑並驗證通過後自動維護與更新。

---

## [Phase 4] 行事曆整合與時區時間座標 (Calendar Integration & Timezone)

- **紀錄時間**：2026-08-16 21:05 (UTC+8)
- **修改類型**：[新增] Phase 4: 行事曆整合 (Calendar Integration)
- **涉及檔案**：
  - `mcp_server/third_party/calendar_server.py` (新增)
  - `config/mcp_servers.json` (修改，註冊 `calendar_server`)
  - `app/agent/nodes.py` (修改，動態注入當前時間與時區，新增行事曆相對時間意圖轉換)
  - `app/mcp/manager.py` (修改，支援高風險寫入/刪除操作權限攔截記錄)
  - `app/mcp/client.py` (修改，擴充彈性指令與參數支援)
  - `app/cli.py` (修改，新增行事曆指令提示)
  - `tests/test_calendar_server.py` (新增)
  - `tests/test_calendar_integration.py` (新增)
  - `docs/development-log/2026-08-16-p4-01-calendar-integration.md` (新增)
- **修改原因 / 邏輯**：
  - 遵循 Protocol First 原則，建立獨立的 Calendar MCP Server（`calendar_server.py`），提供 `query_events`、`add_event`、`update_event`、`delete_event` 四大標準工具。
  - 實作強韌時間解析器（`parse_flexible_datetime`），容錯支援多種常見日期與 ISO 8601 格式，防止格式微小偏差導致執行錯誤。
  - 在 Agent 系統提示詞中動態注入 `Current Time` 與 `Timezone`，使大腦具備時間錨點（Time Anchor），能精準推算「明天下午 3 點」、「後天」等相對時間。
  - 強化安全權限邊界：針對 `add_event`、`update_event`、`delete_event` 等高風險寫入/刪除操作，自動標記 `WRITE / MUTATION` 並記錄 `[PERMISSION REQUIRED: WRITE/DELETE]` 稽核記錄。
- **對整體架構影響**：
  - JARVIS 擁有了第一套真正的時間與行程管理能力。
  - 所有的行事曆資料庫邏輯（SQLite）與外部 API（未來可無縫切換 Google Calendar）均被嚴格隔離在 MCP Server 中，LangGraph Agent 核心維持純粹的協議調用。
- **如何測試**：
  1. 伺服器單元測試：`uv run --extra dev pytest tests/test_calendar_server.py`（驗證容錯時間解析與 CRUD 資料庫操作）。
  2. Agent 整合測試：`uv run --extra dev pytest tests/test_calendar_integration.py`（驗證相對時間推算、MCP 路由與安全性標記）。
  3. CLI 互動測試：`uv run python -m app.cli`（嘗試「幫我預約明天下午 3 點開會」與「查詢明天的行程」）。
  4. 全套回歸測試：`uv run --extra dev pytest`（34/34 測試全數通過）。

### Beginner Explanation (新手解釋：AI 是怎麼理解相對時間的？)

> 🕒 **什麼是「時間錨點（Time Anchor）」？**
> 
> - 當你跟朋友說「明天下午 3 點一起喝咖啡」，朋友的大腦會立刻看一眼手錶（知道今天是 8 月 16 日），然後在行事曆上翻到 8 月 17 日 15:00。
> - **AI 本身是沒有手錶的**！如果沒有告訴它現在幾點，當你說「明天」，它根本不知道明天是哪一天。
> - 因此，我們在每次對話前，都會悄悄把「現在是 2026-08-16 21:05、時區 Asia/Taipei」寫在小紙條上塞給 AI 大腦。
> - AI 拿著這張小紙條（時間錨點），就能透過數學計算：`2026-08-16` + `1 天` ➔ 算出精準的 `2026-08-17T15:00:00`，並交給 Calendar 伺服器記錄下來！

---

## [Special Detour] LINE 通訊介面模組 (LINE Webhook Gateway x LangGraph)

- **紀錄時間**：2026-08-16 20:43 (UTC+8)
- **修改類型**：`[Special Detour: LINE UI]` LINE Gateway 模組
- **涉及檔案**：
  - `app/interfaces/line_gateway.py` (新增)
  - `app/interfaces/__init__.py` (新增)
  - `app/agent/graph.py` (修改)
  - `.env.example` (修改)
  - `tests/test_line_gateway.py` (新增)
  - `docs/development-log/2026-08-16-special-detour-line-gateway.md` (新增)
- **Architecture Note:**
  - **解耦設計 (Decoupling Architecture)**：LINE Gateway 置於獨立介面層，作為純適配器。LangGraph 核心與 MCP 總管保持獨立，可隨時切換至 CLI、Web 或其他通訊介面。

---

## [Phase 3] 第三方 MCP 整合與 MCP Manager 總管模組 (Third-party MCP Integration)

- **紀錄時間**：2026-08-16 20:02 (UTC+8)
- **修改類型**：[新增/升級] Phase 3: Third-party MCP Integration (第三方 MCP 整合)
- **核心內容**：
  - 外部設定檔驅動架構、`MCPManager` 多伺服器連線池、SQLite 筆記資料庫伺服器與安全權限邊界模型（`READ_ONLY` vs `WRITE / MUTATION`）。

---

## [Phase 2] 自有 MCP 伺服器與 Agent 對接 (Own MCP Server & Integration)

- **紀錄時間**：2026-08-16 19:38 (UTC+8)
- **修改類型**：[新增/升級] Phase 2: Own MCP Server (自有 MCP 伺服器)
- **核心內容**：
  - 官方 Python MCP SDK 2.0.0 (`MCPServer`) stdio 伺服器與 `MCPStdioClient` 客戶端連接器。

---

## [Phase 1] 基礎 LangGraph 狀態圖代理人 (Basic LangGraph Agent)

- **紀錄時間**：2026-08-16 18:34 (UTC+8)
- **變更類型**：[新增] Phase 1: 基礎 LangGraph Agent
- **核心內容**：
  - `AgentState`、`agent` 節點、`tools` 節點、`should_continue` 條件路由與 CLI 介面。
