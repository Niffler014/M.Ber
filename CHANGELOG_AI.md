# CHANGELOG_AI — JARVIS 專案變更紀錄

此文件遵循 AI 自動變更紀錄協議（Changelog Protocol），由 AI 助理在每次完成階段性里程碑並驗證通過後自動維護與更新。

---

## [Phase 5.1] 記憶子系統架構與合約設計 (Memory Architecture & Contract Design)

- **紀錄時間**：2026-08-16 22:23 (UTC+8)
- **修改類型**：[新增/架構] Phase 5.1: 記憶子系統合約與倉儲架構 (Memory Architecture & Contract)
- **涉及檔案**：
  - `memory/models.py` (新增)
  - `memory/repository.py` (新增)
  - `memory/sqlite.py` (新增)
  - `memory/service.py` (新增)
  - `memory/__init__.py` (修改，完整匯出)
  - `tests/test_memory_contract.py` (新增)
  - `tests/test_memory_sqlite.py` (新增)
  - `docs/development-log/2026-08-16-p5-01-memory-architecture-contract.md` (新增)
- **修改原因 / 邏輯**：
  - 在實作資料庫與 Agent 記憶整合前，先建立穩定的領域合約與倉儲分層邊界（Dependency Inversion）。
  - 核心 Agent/Orchestrator 僅依賴 `MemoryService` 提供的高階領域意圖（`remember`, `recall`, `search`, `forget`），絕不直接依賴或操作 SQLite。
  - 實作 `MemoryRepository` 抽象介面，並提供 `InMemoryMemoryRepository`（供單元測試）與 `SQLiteMemoryRepository`（預設儲存於 `data/memory.db`）。
  - 嚴格守護架構不變量：不引入向量資料庫、Embedding 或 RAG，保持架構簡潔、可替換且可解釋。
- **對整體架構影響**：
  - 為 JARVIS 建立了首個正式的 Memory 領域服務層，未來隨時可抽換底層儲存實作而不破壞上層對話與推理邏輯。
  - 現有 Phase 1–4 的所有工具調用、狀態圖路由與 LINE 閘道器完全不受影響。
- **如何測試**：
  1. 合約單元測試：`uv run --extra dev pytest tests/test_memory_contract.py`（驗證純記憶體環境下 remember/recall/search/forget 領域行為）。
  2. SQLite 整合測試：`uv run --extra dev pytest tests/test_memory_sqlite.py`（驗證真實 SQLite 檔案建表、參數化 SQL 與 JSON 欄位轉換）。
  3. 全套回歸測試：`uv run --extra dev pytest`（41/41 測試全數通過）。

### Beginner Explanation (新手解釋：什麼是「倉儲模式」？)

> 🗄️ **想像你開了一家便利商店**：
> 
> - **店長（MemoryService）**：負責接待客人，處理「請幫我記住/找找這件商品」的需求。
> - **倉庫管理員（MemoryRepository 介面）**：店長只需要跟倉管說「我要存入/拿取商品」，不用親自去翻箱倒櫃。
> - **倉庫本身（SQLiteMemoryRepository / InMemoryMemoryRepository）**：
>   - 平時可以用地下室的實體鐵架（SQLite）把東西存下來。
>   - 做消防演習或新品測試時，可以用臨時折疊桌（InMemory）快速模擬，測完直接收掉，完全不會弄亂正式庫存！
> - 這就是「依賴反轉」的威力：店長（Agent / Service）永遠不需要知道地下室的鐵架是用什麼螺絲鎖的！

---

## [Phase 4.5] 架構審查、清理與套件邊界校正 (Architecture Cleanup & Packaging Boundary)

- **紀錄時間**：2026-08-16 22:08 (UTC+8)
- **修改類型**：[維護/清理] Phase 4.5: Architecture Cleanup
- **核心內容**：
  - 同步 README / AGENTS.md / PROJECT_SPEC / protocol-versions 之狀態與版本號至 `0.5.0`。
  - 修正 `pyproject.toml` 套件探索範圍為 `["app*", "mcp_server*", "services*", "memory*"]`。
  - 自 Git 追蹤快取移除 `jarvis_agent.egg-info/`，並加入 `.gitignore`。

---

## [Phase 4] 行事曆整合與時區時間座標 (Calendar Integration & Timezone)

- **紀錄時間**：2026-08-16 21:05 (UTC+8)
- **修改類型**：[新增] Phase 4: 行事曆整合 (Calendar Integration)
- **核心內容**：
  - Calendar MCP Server、容錯時間解析器（`parse_flexible_datetime`）、動態時區時間注入與高風險操作安全邊界攔截。

---

## [Special Detour] LINE 通訊介面模組 (LINE Webhook Gateway x LangGraph)

- **紀錄時間**：2026-08-16 20:43 (UTC+8)
- **修改類型**：`[Special Detour: LINE UI]` LINE Gateway 模組

---

## [Phase 3] 第三方 MCP 整合與 MCP Manager 總管模組 (Third-party MCP Integration)

- **紀錄時間**：2026-08-16 20:02 (UTC+8)
- **修改類型**：[新增/升級] Phase 3: Third-party MCP Integration

---

## [Phase 2] 自有 MCP 伺服器與 Agent 對接 (Own MCP Server & Integration)

- **紀錄時間**：2026-08-16 19:38 (UTC+8)
- **修改類型**：[新增/升級] Phase 2: Own MCP Server

---

## [Phase 1] 基礎 LangGraph 狀態圖代理人 (Basic LangGraph Agent)

- **紀錄時間**：2026-08-16 18:34 (UTC+8)
- **變更類型**：[新增] Phase 1: 基礎 LangGraph Agent
