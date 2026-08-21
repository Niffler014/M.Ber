# Phase 8 P8-03.5 — Real Conversation Integration & Production Planner Fix

## Date
2026-08-21

## Phase
Phase 8 — P8-03.5 (Real Conversation Integration & Production Planner Fix)

## Goal
修復 M.Ber 在實際 Web UI 聊天測試中發現的「假成功範本 (Placeholder Template)」與「閒聊/實體需求語意誤判」問題，讓 M.Ber 在執行 `LOCAL` 任務時能調用真實 ChatModel 進行無工具直接推理（Tool-free reasoning），並確保 Planner 具備完整的語意理解與架構單一 Composition Root。

---

## Why the Change was Necessary
在 Phase 8 前期，系統為了在無 API Key 的離線/測試環境下維持測試通過，在 `LocalExecutor` 與 `MockDeterministicPlanningBackend` 中採用了簡化的關鍵字比對與預設佔位文字（`"已為您處理完成：{goal}"`）。

這導致了兩個核心問題：
1. **閒聊假成功**：當使用者輸入「我肚子很餓」等一般日常對話時，系統回傳 `已為您處理完成：我肚子很餓`，而非真實模型生成的親切回應。
2. **語意比對誤判**：離線規則容易將自然語言查詢（例如「我想配電腦」）誤判或無法正確映射到遠端 A2A Agent（如 PCforge），或將非組裝電腦的普通提及誤判。
3. **缺少 LOCAL 真實推論通道**：先前的架構中，Planner 為 Single Routing Authority，但 LOCAL 節點缺乏與真實 `ChatModel` 的標準適配器（Adapter），且沒有統一注入系統提示詞（System Prompt）與多輪對話歷史（Conversation History）。

---

## Files Changed
1. **`app/orchestration/model_factory.py`** (NEW):
   - 建立集中且明確的 `get_chat_model()` Factory，根據環境變數 `MODEL_PROVIDER` 與 `MODEL_NAME` 明確初始化 LangChain `BaseChatModel`（支援 OpenAI, Anthropic, Google Gemini, Ollama, DeepSeek），不進行多 Key 猜測，預設為 tool-free。
2. **`app/orchestration/local_reasoning.py`** (NEW):
   - 實作 `LocalReasoningAdapter`，負責將使用者的對話意圖與 `ExecutionContext.metadata["messages"]` 轉為提示詞發送給 `ChatModel`，並提供自訂離線知識庫備援；當無模型且無備援時明確拋出例外而非假冒成功。
3. **`app/orchestration/models.py`** (MODIFY):
   - 在 `ExecutionContext` 中加入 `metadata: Dict[str, Any]`，讓呼叫端（如 Web API / CLI）能傳遞對話訊息歷史及上下文資訊。
4. **`app/orchestration/executors.py`** (MODIFY):
   - 更新 `LocalExecutor`，支援捕捉 `TimeoutError` 並轉換為 `ExecutionStatus.TIMEOUT`，將 Adapter 傳回的純字串安全包裝為 `ExecutionResult`。
5. **`app/orchestration/orchestrator.py`** (MODIFY):
   - 確保在執行 topological tasks 時，將 context 內的 `metadata` 正確繼承至各子任務的 `task_context`。
6. **`app/orchestration/planner.py`** (MODIFY):
   - 增強 `MockDeterministicPlanningBackend` 的語意過濾（區分一般提及與組裝需求），並確保在提供 `ChatModel` 時明確選用 `LangChainStructuredPlanningBackend`，並輸出明確可觀測的日誌 `[Planner] backend=...`。
7. **`app/orchestration/service.py`** (MODIFY):
   - 統一 production composition root，在 startup 時執行安全 A2A discovery（若遠端 peer 離線不拋例外中斷系統），並在 discovery 完成後建立快照 `CapabilitySummary`；註冊 `LocalReasoningAdapter` 至 `LocalExecutor`。保留 P8-04 的所有 MCP Status 與 Activity Recorder 介面。
8. **`tests/test_local_reasoning.py`** (NEW):
   - 撰寫 8 項單元測試，涵蓋 ChatModel 調用、無模型時的安全失敗、超時處理、訊息歷史傳遞、離線知識備援等情境。
9. **`tests/test_planner.py`** (MODIFY):
   - 增加負向語意測試（「我昨天買了一台電腦」、「我的電腦最近很慢」不應路由至 A2A），並測試 Explicit Backend Logging、Discovery 失敗容錯與 CapabilitySummary 快照建立。
10. **`tests/test_web_api.py`** (MODIFY):
    - 增加 Web Chat 整合測試，驗證 LOCAL 真實對話與 A2A「我想配電腦」的真實執行痕跡。

---

## Before / After Architecture

### Before:
```text
User Request
   ↓
Web API Gateway
   ↓
Planner (MockDeterministic / Keyword)
   ↓
Orchestrator → Router
   ├─ LOCAL  ──> LocalExecutor (直接傳回 "已為您處理完成：{goal}" 佔位字串 ❌)
   ├─ MCP    ──> MCPExecutor
   └─ A2A    ──> A2AExecutor
```

### After:
```text
User Request (with Conversation History)
   ↓
Web API Gateway (Single Composition Root)
   ↓
Capability Discovery (MCP Tools + A2A Skills) ──> CapabilitySummary Snapshot
   ↓
Planner ([Planner] backend=structured_llm / deterministic_offline)
   ↓
Orchestrator (Topological execution with Context metadata)
   ↓
Router
   ├─ LOCAL ──> LocalExecutor ──> LocalReasoningAdapter ──> ChatModel (Tool-free LLM Reasoning ✅)
   │                                                 └──> Explicit Fallback / Failure
   ├─ MCP   ──> MCPExecutor ──> MCPActivityRecorder (P8-04 Preserved)
   └─ A2A   ──> A2AExecutor ──> Peer Remote Agent (PCforge)
   ↓
ResultAggregator ──> Final User Response + ExecutionTrace
```

---

## Important Code Concepts

### 1. Tool-Free Local Reasoning
在 LangChain/LangGraph 架構中，Planner 扮演「單一路由決策者 (Single Routing Authority)」。當 Planner 判定該步驟屬於一般交談、推理、問答或任務總結時，會路由至 `LOCAL`。
`LOCAL` 執行器呼叫 LLM 時，**絕對不能綁定外部工具或重複呼叫 A2A**，而是將 prompt 與歷史對話傳入無工具模型進行乾淨的文字生成。

### 2. Explicit Model Configuration
避免在程式中寫死「只要有 OpenAI key 就用 OpenAI」的猜測行為，透過 `MODEL_PROVIDER`（如 `openai`, `gemini`, `ollama`）與 `MODEL_NAME` 作為顯式設定來源，金鑰僅作為認證憑證。

### 3. Fail-Safe Over Fake-Success
當未配置 LLM 且無離線知識庫匹配時，系統必須顯式拋出錯誤並標記為 `ExecutionStatus.FAILED`，絕不回傳假裝成功的通用樣板。

---

## Test Results

### 1. Python Backend Tests (pytest)
```bash
uv run pytest
```
**Result**: `229 passed in 584.77s (100% PASS)`

涵蓋測試：
- `test_local_reasoning.py` (8 passed)
- `test_planner.py` (30 passed)
- `test_web_api.py` (16 passed)
- `test_mcp_activity.py` (13 passed)
- `test_mcp_executor.py` (10 passed)
- `test_execution_trace.py` (12 passed)
- `test_orchestrator.py` (9 passed)
- 以及所有既有 Phase 0 ~ Phase 7 測試

### 2. React Frontend Tests & Build (vitest + vite)
```bash
npm run test -- --run && npm run build
```
**Result**:
- `3 test files passed (19 tests)`
- `vite build: built in 5.52s (PASS)`

---

## Beginner Explanation
**什麼是「無工具本機推論 (Tool-free Local Reasoning)」？**

想像 M.Ber 是一個管家：
1. **Planner（大腦管家）**：先聽懂你的話，並決定是該派人去查日曆（MCP）、找電腦專家（A2A），還是自己動腦回答（LOCAL）。
2. **如果決定自己回答（LOCAL）**：
   - 以前：管家直接照抄一句「好的，已為你完成：我肚子很餓」（像錄音機一樣假裝回答）。
   - 現在：管家自己認真思考（調用 LLM），並根據你的上文「我肚子很餓」，親切回答：「肚子餓了嗎？附近有一家不錯的麵店，或者你需要我幫你查詢外送嗎？」
3. 這樣 M.Ber 就具備了真實自然的對話能力，同時完整保留了調度外部工具（MCP）與外部代理人（A2A）的強大能力！

---

## Next Step
進入 **Phase 8 P8-05 — Multi-Channel Expansion (LINE Notification & Preferences)**：
1. 實作 LINE Webhook 與通知偏好設定。
2. 整合 MCP Activity / A2A 事件至 LINE 推播通道。
3. 完善 Web UI 上的多通道通知設定面版。
