# 2026-08-21 Phase 8 P8-04 — MCP Activity & Runtime Inspector

## 1. 基礎資訊
- **日期**：2026-08-21
- **階段**：Phase 8 — Web API & Interactive Demo UI (P8-04)
- **目標**：建立 MCP Activity 後端觀測紀錄器、REST API 與 React Web UI Activity 面板，讓使用者即時觀測全域 MCP 工具調用歷史、伺服器狀態與工具權限等級，並為 P8-05 LINE 通知提供穩定透明的事件來源。

---

## 2. 為什麼需要這項變更 (Why)
1. **全域工具可觀測性（Global MCP Observability）**：
   - 既有的 `Execution Trace` 屬於「單次使用者請求的任務時序（Per-Request Trace）」。
   - `MCP Activity` 則是「全系統各伺服器與工具調用的全域活動紀錄（Global Tool Call History）」。
   - 透過統一的活動觀測器，使用者與維運者能清楚掌握：哪些 MCP 工具正在被執行、調用耗時多少毫秒、執行結果是成功、失敗還是逾時。
2. **安全性與資料脫敏邊界（Security & Data Redaction Boundary）**：
   - MCP 工具可能傳入敏感參數或回傳大量隱私資料。
   - `MCPActivityRecorder` 實施嚴格資料脫敏（Data Sanitization）：**絕不記錄參數（arguments）、工具內文（results）、提示詞（prompt）或 Traceback 原始堆疊**，確保前端展示與日誌紀錄安全。
3. **無鎖/低開銷環狀緩衝（In-Memory Bounded History）**：
   - 不引入龐大的外部資料庫（如 Redis / SQLite 新表），採用 Python 原生線程安全 `collections.deque(maxlen=100)` 與 `threading.Lock`，極致輕量且存取迅速。

---

## 3. 變更的檔案清單 (Files Changed)
- `app/mcp/activity.py` [NEW]：定義 `MCPActivityRecord` 與線程安全環狀緩衝區 `MCPActivityRecorder`，提供 `get_default_mcp_recorder()` 全域單例。
- `app/mcp/manager.py` [MODIFY]：增加 `get_tools_metadata()` 與 `get_server_count()` 安全公開元數據查詢方法。
- `app/orchestration/executors.py` [MODIFY]：更新 `MCPExecutor`，在執行工具成功、逾時或失敗時，即時登錄活動觀測紀錄（包含安全等級 `READ_ONLY` / `WRITE` 與執行耗時 `duration_ms`）。
- `app/interfaces/web/models.py` [MODIFY]：新增 `McpToolInfo`、`McpStatusResponse`、`McpActivityItem`、`McpActivityResponse` DTO 模型。
- `app/interfaces/web/gateway.py` [MODIFY]：新增 `GET /api/mcp/status` 與 `GET /api/mcp/activity` HTTP 端點，支援 limit 參數與健康快照。
- `app/interfaces/web/__init__.py` [MODIFY]：匯出新增之 MCP DTO 模型。
- `frontend/src/api/types.ts` [MODIFY]：新增前端 TypeScript MCP 狀態與活動介面定義。
- `frontend/src/api/client.ts` [MODIFY]：新增 `getMcpStatus()` 與 `getMcpActivity()` API 客戶端函式。
- `frontend/src/components/McpActivityPanel.tsx` [NEW]：實作 MCP 狀態指標、可用工具摺疊列表、最新活動卡片清單與定時自動輪詢。
- `frontend/src/components/ExecutionTracePanel.tsx` [MODIFY]：整合 Tab 切換器（`[ Trace ]` 與 `[ MCP Activity ]`），使桌面端與手機端 Drawer 完美共用右側面板空間。
- `frontend/src/index.css` [MODIFY]：新增 Tab 按鈕、MCP 工具卡片、安全權限徽章（`Read only` / `Writes data`）與活動狀態配色。
- `tests/test_mcp_activity.py` [NEW]：13 項後端單元與整合測試。
- `frontend/tests/mcpActivity.test.tsx` [NEW]：5 項前端組件互動與狀態測試。
- `README.md` [MODIFY]：更新 Phase 8 P8-04 完成狀態。

---

## 4. 架構演進 (Before / After Architecture)

### Before (Phase 8 P8-03)
```text
React Chat UI
    │ (POST /api/chat/stream)
    ▼
FastAPI Gateway
    │
    ▼
OrchestrationService
    ├─► Planner ──► TaskPlan
    ├─► Router ──► Local / MCP / A2A
    │                 └─► MCPExecutor (未記錄全域觀測活動)
    └─► Aggregator ──► Response
```

### After (Phase 8 P8-04)
```text
React Web UI [Tabs: Execution Trace | MCP Activity]
    │                                  │
    │ (SSE /api/chat/stream)          │ (GET /api/mcp/status, GET /api/mcp/activity)
    ▼                                  ▼
FastAPI Gateway ───────────────────────┼───────────┐
    │                                  │           │
    ▼                                  │           │
OrchestrationService                   │           │
    ├─► Planner ──► TaskPlan           ▼           ▼
    ├─► Router ──► Local / MCP / A2A   MCPManager  MCPActivityRecorder
    │                 └─► MCPExecutor (Thread-Safe deque maxlen=100)
    │                         │ (record: tool, server, duration, status, safety)
    │                         └───────────────────────►
    └─► Aggregator ──► Response
```

---

## 5. 核心程式概念 (Important Concepts)

### 1. 線程安全環狀緩衝（Bounded History with Lock）
```python
class MCPActivityRecorder:
    def __init__(self, max_history: int = 100) -> None:
        self._max_history = max_history
        self._history: deque[MCPActivityRecord] = deque(maxlen=max_history)
        self._lock = threading.Lock()

    def record(self, tool_name: str, server_name: str, status: str, ...) -> MCPActivityRecord:
        with self._lock:
            self._history.appendleft(record)
```
- `appendleft` 讓最新發生的活動永遠排在最前面索引 `0`。
- `deque(maxlen=100)` 自動維護容量上限，當超過 100 筆時，最舊的一筆會自動被擠出釋放，永不佔用多餘記憶體。

### 2. 嚴格安全性防護（Strict Data Sanitization）
- 不儲存使用者 prompt 或 tool 參數字典。
- 發生例外時，使用 `str(error).split("\n")[0][:200]` 自動截斷多行堆疊資訊，防止敏感檔案路徑洩漏。
- 工具安全權限等級自動依前綴分類為 `read_only` 與 `write`，讓前端一眼辨識危險程度。

---

## 6. 測試驗證 (Test Results)

### 後端測試 (pytest)
執行 23 項 MCP 核心與活動端點測試：
```bash
uv run pytest tests/test_mcp_activity.py tests/test_mcp_executor.py
```
**結果**：`23 passed in 28.73s`

測試覆蓋重點：
1. `test_activity_recorder_bounded_history`：驗證容量上限與 FIFO 擠出行為。
2. `test_activity_recorder_preserves_order`：驗證時間倒序排列。
3. `test_activity_recorder_thread_safe`：驗證多執行緒並行寫入一致性。
4. `test_activity_recorder_cleans_error_summary`：驗證異常訊息脫敏。
5. `test_mcp_status_endpoint`：驗證狀態、工具數、伺服器數正確。
6. `test_mcp_status_does_not_expose_internal_config`：驗證絕不外洩內部路徑或環境變數。
7. `test_mcp_activity_endpoint_empty`：驗證初始無紀錄回傳空清單。
8. `test_mcp_activity_records_success / failure / timeout`：驗證各種狀態準確記錄。
9. `test_mcp_activity_limit`：驗證 limit 參數有效性。
10. `test_mcp_activity_does_not_store_arguments_or_results`：驗證敏感參數隔離。
11. `test_a2a_only_request_does_not_generate_mcp_activity`：驗證純 A2A 請求不產生偽 MCP 活動。

### 前端測試 (vitest & build)
```bash
npm run test
npm run build
```
**結果**：
- `Test Files: 3 passed (3), Tests: 19 passed (19)`
- `vite build`: `dist/assets/index-LOZSQcOM.js 295.70 kB │ gzip: 91.74 kB` (5.05s)

---

## 7. 遇到的挑戰與解決方案 (Problems Encountered & Solutions)
- **問題**：部分 Mock MCPManager 在單元測試中未定義 `tool_routes` 字典或 `evaluate_safety_level` 方法，導致 `MCPExecutor` 呼叫屬性時觸發 `AttributeError`。
- **解法**：在 `MCPExecutor` 中採用 Pythonic 鴨子型別安全存取：`getattr(self.mcp_manager, "tool_routes", {})` 與 `getattr(self.mcp_manager, "evaluate_safety_level", None)`，提供安全的預設回退值，大幅提升適配性與測試隔離度。

---

## 8. 新手教學 / 觀念解析 (Beginner Explanation)

> **小比喻：什麼是 MCP Activity Panel？**
>
> 想像你的 AI 助理是一間大工廠的總指揮官：
> - **Execution Trace（執行軌跡）** 就像是「某一筆訂單的專屬進度表」，記錄著這張訂單經過規劃、零件採購、組裝完成的整個過程。
> - **MCP Activity Panel（工具活動監控面板）** 就像是工廠牆上掛著的「全廠即時儀表板」，顯示著全廠總共有幾部機器連線中、剛剛哪部機器被啟動了、運轉了幾毫秒、運轉是否正常。
> - 在這個監控面板上，我們不會把客戶的隱私資料寫在牆上（**安全脫敏**），但能隨時掌握所有機器的健康狀態與運作情況！

---

## 9. 下一步 (Next Step)
進入 **Phase 8 P8-05 — Multi-Channel Expansion (LINE Notification & Preferences)**：
1. 實作 LINE Webhook 雙向轉接與通知推播機制。
2. 整合使用者通知偏好設定（Notification Preferences）。
3. 串接 MCP 工具高風險操作之主動推播通知。
