# Phase 7 P7-07 開發日誌：LangGraph 主流程整合與單一調度中樞 (Single Routing Authority)

## 1. 基本資訊
- **日期**：2026-08-21
- **階段**：Phase 7 (P7-07)
- **目標**：將 Planner、Orchestrator、Router、Executors (LOCAL / MCP / A2A)、MemoryAdapter 與 ResultAggregator 正式接入 LangGraph 主流程，實現單一頂層路由權威（Single Routing Authority），並確保全系統 163 項測試 0 regression。

---

## 2. 為什麼需要這次修改？
在 Phase 6 與更早階段中：
1. **意圖決策分散**：LangGraph 的 `agent_node` 內部同時混合了 Phase 6 的確定性 A2A 比對 (`A2ADelegator.match_and_delegate`)、MCP 工具呼叫分支與本地回應，缺乏統一的路由標準與多步驟規劃能力。
2. **缺乏多步驟協同能力**：例如「先找外部專業代理人配單，再把配單結果寫入長期記憶庫」這樣的跨協定循序任務，無法在既有 LangGraph 節點中由統一的調度層協調完成。
3. **架構分層不清晰**：頂層既有 `agent_node` 直接介入了特定的外部通訊協議細節。

P7-07 作為 Phase 7 的最終整合里程碑，建立了 `OrchestrationService` 作為 Application Boundary & Composition Root，將所有頂層意圖統一交由 Planner 規劃為 `TaskPlan`，再由 `Orchestrator` 依賴驅動執行並由 `ResultAggregator` 彙整輸出，達成 **Single Routing Authority**。

---

## 3. 架構前後對比 (Before / After Architecture)

### 【Before - Phase 6 分散路由】
```text
User Request
    ↓
LangGraph [agent_node]
    ├─► if "配單" ──► A2ADelegator (直接發送 A2A RPC) ──► 回覆字串
    ├─► if "行程/時間" ──► tool_calls ──► [tools_node] ──► MCP Server
    └─► else ──► LLM / 本地文字回覆
```

### 【After - Phase 7 統一調度中樞 (Single Routing Authority)】
```text
User Request
    ↓
LangGraph [agent_node]
    ↓
OrchestrationService (Application Boundary / Composition Root)
    ↓
Planner.plan(user_goal) ──► TaskPlan (1..N SubTasks with depends_on)
    ↓
Orchestrator.execute_plan(plan)
    ↓
Router.route(subtask)
    ├─► LOCAL ──► LocalExecutor (MemoryAdapter, General Reasoning, Fallback)
    ├─► MCP   ──► MCPExecutor   (MCPManager, Multi-Server Tool Dispatch)
    └─► A2A   ──► A2AExecutor   (AgentDiscoveryService, Peer RPC Client)
    ↓
List[ExecutionResult]
    ↓
ResultAggregator.aggregate(plan, results) ──► AggregatedResult
    ↓
Final Response Synthesis Layer ──► AIMessage ──► User
```

---

## 4. 變更的檔案清單
1. `app/orchestration/service.py` [NEW]
   - 建立 `OrchestrationService` 與 `default_local_reasoning_handler`。
   - 封裝 Planner、Orchestrator、Router、Executors (LOCAL, MCP, A2A) 與 ResultAggregator 之組裝與執行生命週期。
2. `app/orchestration/__init__.py` [MODIFY]
   - 匯出 `OrchestrationService`。
3. `app/orchestration/executors.py` [MODIFY]
   - 優化 `A2AExecutor` 的 Artifacts 與輸出字串格式化，確保產物名稱與狀態完整呈現。
4. `app/orchestration/planner.py` [MODIFY]
   - 增強 `MockDeterministicPlanningBackend` 的 A2A 技能比對與 MCP 工具關鍵字辨識。
5. `app/agent/nodes.py` [MODIFY]
   - `create_agent_node` 支援注入 `orchestration_service`，啟用時完全委任單一調度中樞處理。
6. `app/agent/graph.py` [MODIFY]
   - `create_agent_graph` 支援注入 `orchestration_service`、`planner`、`orchestrator` 與 `use_orchestration` 參數，並新增 `create_orchestrated_graph` 工廠函式。
7. `app/cli.py` [MODIFY]
   - CLI 正式啟用 Phase 7 Orchestration 模式 (`use_orchestration=True`)。
8. `tests/test_langgraph_orchestration.py` [NEW]
   - 8 項端到端整合測試：LOCAL 推理、A2A 委派、MCP 工具、多步驟工作流 (A2A ➔ Memory)、部分失敗、全失敗、自訂 LLM 注入與驗證頂層絕不調用 legacy delegator。

---

## 5. 重要程式觀念解析 (Beginner Explanation)

### 什麼是「單一路由權威 (Single Routing Authority)」？
想像一間大公司裡如果每位專員都各自私下接外包案（有些丟給廠商、有些自己做、有些呼叫工具），管理將會極度混亂。
**Single Routing Authority** 就像公司設立了專門的「專案規劃部（Planner）」：
- 無論客戶提出什麼需求，一律先交給 Planner 拆解成待辦清單（`TaskPlan`）。
- 每個子任務標註好是由內部處理（`LOCAL`）、使用外部工具（`MCP`）、還是委派給外部專家代理人（`A2A`）。
- 任何底層執行元件都不能越權自行決定跳過規劃，確保所有任務都在可控、可觀測的軌道上運作。

---

## 6. 測試驗證結果 (Test Results)
執行完整專案測試套件：
```bash
uv run pytest
```
測試結果：
```text
======================= 163 passed in 94.66s (0:01:34) ========================
```
- **通過總數**：163 passed / 0 failed。
- **涵蓋範圍**：Smoke 測試、A2A 通訊、MCP 管理、Memory 儲存庫、Orchestration 領域模型、Router、Executors、Planner、Dependency Execution、Result Aggregator、以及 LangGraph 整合。

---

## 7. 下一步 (Next Step)
- Phase 7 核心目標已全數圓滿達成！
- 後續可進入 Phase 8 (LLM-Assisted Autonomous Planning & Dynamic Re-planning) 或 Phase 9 (A2A Server Export & Discovery Registry Server)。
