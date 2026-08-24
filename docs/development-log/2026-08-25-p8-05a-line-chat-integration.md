# Development Log: P8-05A LINE Bidirectional Chat Integration

## 1. 基本資訊
- **日期**: 2026-08-25
- **階段**: Phase 8 - P8-05A: LINE Bidirectional Chat Integration
- **目標**: 讓 LINE 正式成為 M.Ber 的第二個通訊通道（Channel），與 Web UI 共用同一套核心調度大腦（Single Routing Authority / Single Application Core），移除 legacy agent loop 與重複實例化邏輯。

---

## 2. 背景與問題分析 (Why)

### 現狀痛點
在 Phase 5/6 開發期間，LINE Gateway 直接在模組頂層建構了自己的 `MCPManager` 與 `create_agent_graph(use_orchestration=True)`，導致：
1. **多重實例 (Dual Core)**：Web API 與 LINE Gateway 各自維護獨立的工具與調度實例，無法共享同一個 Composition Root。
2. **缺乏安全格式化 (Long Message Risk)**：LINE TextMessage 單則上限為 5000 字元，且單次 reply 上限為 5 則。若 Planner/LLM 產出長篇報告，缺乏安全切分保護。
3. **無一致對話身分識別 (Raw User ID Leak)**：直接將 LINE `user_id` 作為 key 與 log 輸出，缺少通道中立命名空間（`line:<USER_ID>`）與個資遮罩。
4. **錯誤處理邊界**：若調度拋出例外，可能中斷 Webhook 甚至外洩伺服器內部堆疊。

---

## 3. 架構設計與原則 (Architecture)

### 核心原則：Channel Adapter ≠ Agent Brain
所有通道（Web Gateway、LINE Gateway、CLI）均為「周邊轉接器（Channel Adapters）」，僅負責：
- 接收通道事件（HTTP JSON / LINE Webhook Event / CLI Stdin）
- 驗證通道合法性（CORS / LINE HMAC-SHA256 Signature）
- 轉換為統一 LangChain `HumanMessage`
- 呼叫唯一的頂層調度權威 `OrchestrationService.invoke_with_details(...)`
- 將統一回傳的自然語言訊息轉換為通道專屬格式回覆（Web JSON SSE / LINE ReplyMessage）

```text
       +-----------------------+     +------------------------+
       |     Web UI Client     |     |   LINE User (Mobile)   |
       +-----------+-----------+     +-----------+------------+
                   |                             |
                   v (HTTP / SSE)                v (Webhook POST /callback)
       +-----------+-----------+     +-----------+------------+
       |      Web Gateway      |     |      LINE Gateway      |
       | (app/interfaces/web)  |     | (app/interfaces/line)  |
       +-----------+-----------+     +-----------+------------+
                   |                             |
                   +--------------+--------------+
                                  |
                                  v (invoke_with_details)
                   +--------------+--------------+
                   |    OrchestrationService     |
                   |  (Shared Application Core)  |
                   +--------------+--------------+
                                  |
               +------------------+------------------+
               |                  |                  |
               v                  v                  v
         +------------+    +-------------+    +-------------+
         |   LOCAL    |    |     MCP     |    |     A2A     |
         | (Reasoning/|    | (Tools/Own/ |    |  (PCforge   |
         |   Memory)  |    |Third-Party) |    | Peer Agent) |
         +------------+    +-------------+    +-------------+
```

---

## 4. 關鍵技術實作

### A. 統一 Composition Root (`app/bootstrap.py`)
- 提供 `create_orchestration_service()` 與 `get_orchestration_service()`。
- 支援單例共用與依賴注入，確保 Web 與 LINE 共用相同的 `ChatModel`、`MCPManager`、`AgentDiscoveryService`、`MemoryService`、`Planner` 與 `Executors`。

### B. 安全訊息切分與格式化 (`app/interfaces/line_formatter.py`)
- 實作 `split_text_into_chunks(text, max_chunk_size=2000, max_chunks=5)`：
  - 優先依雙換行段落切分，其次依換行與標點符號切分，避免字元中斷。
  - 上限 5 則訊息，超長部分附帶省略提示。
- 實作 `mask_user_id(user_id)`：對 LINE User ID 進行安全去識別化日誌記錄（例如 `U_US..._123`）。

### C. LINE Webhook 轉接閘道升級 (`app/interfaces/line_gateway.py`)
- 實作 `create_line_app(orchestration_service=None, ...)` 工廠函式。
- 提取 `event.message.text` ➔ 封裝為 `HumanMessage` ➔ 調用 `service.invoke_with_details(...)`。
- 對話 ID 格式化為 `line:<LINE_USER_ID>`。
- 透過 LINE Messaging API `ReplyMessageRequest` 以 `reply_token` 安全發送回覆。
- 完善例外捕獲與安全 Fallback，絕不向 LINE 使用者外洩 stack trace 或內部 debug metadata。

---

## 5. 變更檔案清單
- **新增** [app/bootstrap.py](file:///e:/code/ive/M.Ber/app/bootstrap.py)：統一應用程式 Composition Root。
- **新增** [app/interfaces/line_formatter.py](file:///e:/code/ive/M.Ber/app/interfaces/line_formatter.py)：LINE 訊息切分與安全格式化工具。
- **修改** [app/interfaces/line_gateway.py](file:///e:/code/ive/M.Ber/app/interfaces/line_gateway.py)：移除 legacy agent loop，升級為 OrchestrationService 轉接器。
- **修改** [tests/test_line_gateway.py](file:///e:/code/ive/M.Ber/tests/test_line_gateway.py)：撰寫 14 項單元與整合測試（全面 Mock 外部網路）。

---

## 6. 測試驗證結果

### 後端 Pytest 測試套件
- `tests/test_line_gateway.py`: **14/14 PASSED (100%)**
- `tests/test_web_api.py`, `tests/test_execution_trace.py`, `tests/test_mcp_activity.py`, `tests/test_pcforge_a2a.py`: **47/47 PASSED (100%)**

### 前端測試套件
- Frontend Vitest: **19/19 PASSED (100%)**
- Frontend Build (`npm run build`): **PASS (0 errors)**

---

## 7. 真機測試與手動驗證指南 (Manual Verification)
1. **本機啟動必要服務**：
   - 啟動 llama.cpp / 本地模型伺服器（Port 8080）。
   - 啟動 PCforge A2A 伺服器：`uv run python -m pcforge`（Port 8001）。
   - 啟動 M.Ber LINE Gateway：`uv run uvicorn app.interfaces.line_gateway:app --reload --port 8000`。
   - 啟動 ngrok 穿透：`ngrok http 8000`。
   - 在 LINE Developers Console 設定 Webhook URL：`https://<ngrok-domain>/callback` 並啟用 Webhook。
2. **LINE App 實測驗證對話**：
   - `「你好」` ➔ 回覆自我介紹（LOCAL general_qa）。
   - `「現在幾點」` ➔ 回覆當前時間（MCP get_current_time）。
   - `「幫我配一台四萬元電腦」` ➔ 回覆 PCforge 硬體規格（A2A pc_recommendation）。
   - `「幫我配電腦然後記住這套配置」` ➔ 回覆配單與記憶庫儲存確認（A2A ➔ LOCAL memory_store）。

---

## 8. 已知限制與下一步 (Known Limitations & Next Steps)
- 本階段（P8-05A）僅實作雙向即時被動回覆（Reply Message）。
- 主動推播訊息（Push Message）、定時排程通知（Scheduled Notifications）及使用者通知偏好將在 **P8-05B / P8-05C** 進行。
