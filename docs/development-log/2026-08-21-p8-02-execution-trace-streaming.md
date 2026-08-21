# Development Log: Phase 8 P8-02 — Execution Trace & SSE Streaming

## 1. 基本資訊
- **日期 (Date)**：2026-08-21
- **階段 (Phase)**：Phase 8 — Web API & Interactive Demo UI (P8-02)
- **目標 (Goal)**：實作執行軌跡收集（Trace Collection）與 Server-Sent Events (SSE) 即時串流端點 (`POST /api/chat/stream`)，讓 Web 前端能即時可視化觀測 Planner、Router、Executor 與 Aggregator 之調度流程，且不與內部協定或狀態耦合。

---

## 2. 為什麼需要這項變更 (Why)
在 P8-01 中，我們建立了 Web Gateway 與基礎 HTTP 契約，但 `POST /api/chat` 的 `trace` 欄位固定為空清單，且前端必須等待整個調度流程全數完成才能收到一次性回應。

為了達成 Phase 8 互動式 Demo 的 UX 目標：
```text
User: 幫我配一台 40000 元電腦然後幫我記住
      ↓
[Web UI 即時狀態流動]
✓ Planning (2 tasks)
✓ A2A · PCforge (pc_recommendation)
✓ Memory (stored)
✓ Complete
      ↓
[Final Response 回應呈現]
```
我們必須：
1. 在 Application 層（`app/orchestration/events.py`）建立獨立於 Web DTO 的內部事件模型與 `TraceSink` 觀察者抽象。
2. 讓調度生命週期各關鍵節點（Request ➔ Planning ➔ Task Started/Completed/Failed/Skipped ➔ Aggregation ➔ Response Ready）結構化推播事件。
3. 提供 `POST /api/chat/stream` SSE 串流端點，使用標準 `text/event-stream` 將進度逐筆推播至瀏覽器。
4. 保持非串流 `POST /api/chat` 同時回傳累積之 `trace` 清單，並透過白名單機制（`SAFE_METADATA_KEYS`）杜絕內部敏感資訊外洩。

---

## 3. 變更檔案清單 (Files Changed)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :--- | :--- |
| `app/__init__.py` | Modified | 將專案標準版本修正為 `0.7.0`（配合 Phase 7 成果）。 |
| `pyproject.toml` | Modified | 同步更新專案宣告版本為 `0.7.0`。 |
| `app/orchestration/events.py` | Created | 定義內部調度事件枚舉 `OrchestrationEventType`、事件模型 `OrchestrationEvent` 及接收器介面 `TraceSink` / `ListEventSink` / `CallbackEventSink` / `CompositeEventSink`。 |
| `app/orchestration/models.py` | Modified | `OrchestrationResponse` 擴充 `events` 欄位，封裝調度週期產出之事件清單。 |
| `app/orchestration/orchestrator.py` | Modified | `execute_plan` 支援傳入 `event_sink`，精確推播 `TASK_STARTED`、`TASK_COMPLETED`、`TASK_FAILED`、`TASK_SKIPPED` 與 `TASK_TIMEOUT`，並採 `time.perf_counter()` 計算單一任務耗時（毫秒）。 |
| `app/orchestration/service.py` | Modified | `invoke_with_details` 整合生命週期事件推播（`REQUEST_RECEIVED`, `PLANNING_STARTED`, `PLAN_CREATED`, `AGGREGATION_COMPLETED`, `RESPONSE_READY`），並支援組合接收器廣播。 |
| `app/interfaces/web/models.py` | Modified | `TraceEvent` 擴充 `event_id`，新增 `to_public_trace_event` 具備安全白名單（`SAFE_METADATA_KEYS`）過濾。 |
| `app/interfaces/web/gateway.py` | Modified | `POST /api/chat` 回傳累積軌跡；新增 `POST /api/chat/stream` SSE 串流端點，以非同步佇列與 Worker 執行緒實現平滑事件推播與連線斷開防護。 |
| `app/interfaces/web/__init__.py` | Modified | 匯出 `to_public_trace_event`。 |
| `tests/test_smoke.py` | Modified | 同步修正版本驗證為 `0.7.0`。 |
| `tests/test_web_api.py` | Modified | 更新累積 Trace 斷言驗證。 |
| `tests/test_execution_trace.py` | Created | 新增 13 個 Trace 與 SSE 測試，覆蓋內部事件、非串流 Trace、SSE 串流、多步驟工作流、A2A 失敗略過 Memory、部分失敗及元數據安全。 |
| `docs/development-log/2026-08-21-p8-02-execution-trace-streaming.md` | Created | 本開發日誌。 |

---

## 4. 架構圖 (Architecture Diagram)

```text
Browser / Frontend
   │
   ├─ POST /api/chat (Non-streaming) ──➔ 回傳 ChatResponse (含完整 trace: [TraceEvent...])
   │
   └─ POST /api/chat/stream (SSE) ────➔ 串流 text/event-stream
                                          ├─ event: trace (planning_started)
                                          ├─ event: trace (plan_created)
                                          ├─ event: trace (task_started)
                                          ├─ event: trace (task_completed / task_skipped)
                                          ├─ event: trace (aggregation_completed)
                                          └─ event: final (ChatResponse payload)
                                                    ↑
                                          Safe Public Mapping (to_public_trace_event)
                                                    ↑
                                          TraceSink (CallbackEventSink / ListEventSink)
                                                    ↑
                   ┌────────────────────────────────────────────────────────────┐
                   │ Application Core (Independent of Web / HTTP DTOs)          │
                   │                                                            │
                   │ OrchestrationService.invoke_with_details()                 │
                   │   ├─ Planner ────➔ emit(PLANNING_STARTED, PLAN_CREATED)    │
                   │   ├─ Orchestrator                                          │
                   │   │    └─ SubTasks ➔ emit(TASK_STARTED, TASK_COMPLETED...) │
                   │   ├─ Aggregator ─➔ emit(AGGREGATION_COMPLETED)             │
                   │   └─ Synthesis ──➔ emit(RESPONSE_READY)                    │
                   └────────────────────────────────────────────────────────────┘
```

---

## 5. 核心觀念解析 (Important Concepts)

### (1) 觀察者模式 (Observer Pattern) 與非侵入式追蹤
- 事件只是調度過程的「觀察者（Observer）」，負責記錄狀態轉折。
- 調度邏輯（Planner、Router、Orchestrator）絕不依賴是否有接收端在聆聽。若無接收端，調度流程依然能順暢執行。

### (2) Server-Sent Events (SSE) 協議格式
- SSE 是一種輕量、基於標準 HTTP 的單向伺服器推播技術，瀏覽器具備原生 `EventSource` 支援。
- 格式規則：
  ```text
  event: trace
  data: {"event_type":"task_started","task_id":"task_001",...}

  event: final
  data: {"message":"回覆內容","status":"success","plan_id":"plan_123"}

  ```
- 每個區塊以兩個連續換行符 `\n\n` 結尾作為事件邊界。

### (3) 同步核心與非同步 SSE 橋接 (Sync/Async Producer-Consumer Pattern)
- M.Ber 底層調度（含 MCP Stdio 子程序通訊、A2A RPC 通訊）為確定性同步 Python 呼叫。
- Web Gateway 使用 Worker Thread 執行調度，並透過 `loop.call_soon_threadsafe(queue.put_nowait, ...)` 將事件推入 `asyncio.Queue`。
- FastAPI 的 `StreamingResponse` 透過 `async def sse_generator()` 逐筆消耗佇列並 yield SSE 封包，實現了無阻塞、高響應的即時串流體驗。

### (4) 依賴失敗時的 Skip 語意追蹤
- 若任務 A（A2A）執行失敗，任務 B（Memory）依賴任務 A：
  - Orchestrator 偵測到前置失敗，直接略過任務 B。
  - 發送 `TASK_SKIPPED` 事件（標記 `status="skipped"`）。
  - **嚴格確保任務 B 絕不會發出 `TASK_STARTED` 事件**，忠實呈現任務從未進入執行的業務語意。

---

## 6. 測試驗證 (Test Results)

### 執行命令
```bash
uv run pytest tests/test_web_api.py tests/test_execution_trace.py
uv run pytest
```

### 測試結果
```text
============================= test session starts =============================
collected 26 items in test_web_api.py and test_execution_trace.py
26 passed in 7.34s

============================= full test suite =============================
194 passed in 112.03s (0:01:52)
0 failed
```

---

## 7. 初學者解說 (Beginner Explanation)
> **什麼是 Execution Trace 與 SSE 串流？**
> 想像你在網路上點了一份複雜的組裝餐點：
> - **先前的模式（Non-streaming）**：你只能盯著網頁發呆等待，直到 5 秒後整份餐點突然做好送上來。
> - **現在的模式（SSE Streaming）**：廚房每做一個步驟，就會發送一則推播進度到你的手機上：
>   - 🛎️ *「經理正在分析菜單 (Planning)...」*
>   - 🛎️ *「已委派 PCforge 專案人員挑選零組件 (A2A)...」*
>   - 🛎️ *「已成功將零組件清單寫入你的個人筆記 (Memory)...」*
>   - 🎉 *「餐點準備完成！以下是您的建議菜單... (Final)」*
>
> 這樣使用者在等待 LLM 或外部工具運算時，能清楚看見每一步在做什麼，大幅提升系統的透明度與操作體驗！

---

## 8. 下一步 (Next Step)
- 進入 **P8-03 — Web Chat Frontend**：
  - 建立現代、簡潔、美觀的 React + Vite 對話介面。
  - 整合 `POST /api/chat/stream`，即時呈現對話氣泡與右側 Execution Trace 執行狀態卡片。
