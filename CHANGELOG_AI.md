# CHANGELOG_AI — JARVIS 專案變更紀錄

此文件遵循 AI 自動變更紀錄協議（Changelog Protocol），由 AI 助理在每次完成階段性里程碑並驗證通過後自動維護與更新。

---

## [Special Detour] LINE 通訊介面模組 (LINE Webhook Gateway x LangGraph)

- **紀錄時間**：2026-08-16 20:43 (UTC+8)
- **修改類型**：`[Special Detour: LINE UI]` LINE Gateway 模組
- **涉及檔案**：
  - `app/interfaces/line_gateway.py` (新增)
  - `app/interfaces/__init__.py` (新增)
  - `app/agent/graph.py` (修改，支援 `checkpointer` 參數與狀態持久化)
  - `.env.example` (修改，新增 LINE Channel 金鑰配置)
  - `tests/test_line_gateway.py` (新增)
  - `docs/development-log/2026-08-16-special-detour-line-gateway.md` (新增)
- **修改原因 / 邏輯**：
  - 建立 FastAPI Webhook Endpoint（`/callback`），接收來自 LINE Platform 的推播訊息事件。
  - 使用 HMAC-SHA256 驗證 `X-Line-Signature` 簽章，防止非法與偽造請求。
  - 將 LINE `user_id` 映射為 LangGraph 的 `thread_id`，搭配 `MemorySaver` 確保不同使用者具備獨立且隔離的連續對話歷史。
  - 觸發 LangGraph Agent 運算與 MCP 工具調用後，透過 LINE Messaging API 將結果回覆給使用者。
- **Architecture Note:**
  - **解耦設計 (Decoupling Architecture)**：本次實作的 LINE Gateway 置於獨立介面層（`app/interfaces/line_gateway.py`），純粹扮演「外部通訊轉接適配器（Adapter / Gateway）」角色。LangGraph 核心（`app/agent/`）與 MCP 總管（`app/mcp/`）完全維持獨立與純粹，不依賴任何 LINE 特定的 SDK 或資料結構。這確保了 JARVIS 核心大腦具備極致的模組化與可攜性，未來可以無縫切換或同時並行 CLI 終端機、Streamlit Web UI、Discord 或 Slack 等任何介面！
- **對整體架構影響**：
  - JARVIS 正式具備從本機終端機走向行動通訊軟體（LINE）的實時互動能力，且支援多使用者並行獨立對話記憶。
- **如何測試**：
  1. 單元測試：`uv run --extra dev pytest tests/test_line_gateway.py`（驗證 `/health`、缺少/錯誤簽章 400 阻擋、合法簽章解析與多使用者 `thread_id` 記憶隔離）。
  2. 本機除錯：啟動 `uv run uvicorn app.interfaces.line_gateway:app --reload --port 8000` 並搭配 `ngrok http 8000` 連接 LINE Developers Webhook。
  3. 全套回歸測試：`uv run --extra dev pytest`（29/29 測試全數通過）。

### Beginner Explanation (新手解釋：什麼是 Webhook 與 thread_id 映射？)

> 📮 **什麼是 Webhook（即時掛號通知）？**
> 
> - **傳統輪詢（Polling）**：就像你每隔 3 秒跑去信箱看「有我的信嗎？」，非常耗電且浪費時間。
> - **Webhook（掛號通知）**：當有人在 LINE 傳訊息給你時，LINE 伺服器會「主動按門鈴（HTTP POST）」把信送到你的門口（`/callback` 端點）。
> 
> 🧠 **什麼是 `thread_id` 映射（獨立記憶抽屜）？**
> 
> - 想像 JARVIS 是一個管家，每位加好友的 LINE 使用者都有一個專屬號碼（`user_id`，如 `U_ALICE` 與 `U_BOB`）。
> - JARVIS 在大腦裡為每個人開了一個「獨立抽屜（`thread_id`）」。
> - 當 Alice 說「我叫愛麗絲」，JARVIS 把記憶收進 Alice 的抽屜；當 Bob 來說話時，JARVIS 打開 Bob 的抽屜，完全不會把 Alice 的祕密搞混！

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
