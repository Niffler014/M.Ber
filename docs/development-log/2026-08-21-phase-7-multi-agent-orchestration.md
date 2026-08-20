# Phase 7 — Multi-Agent & Tool Orchestration

## Goal
Phase 7 的核心目標是為 M.Ber 建立企業級、可擴充且具備依賴傳播能力的 **多代理人與多工具調度中樞（Multi-Agent & Tool Orchestration Layer）**。
將原本分散在各節點的決策邏輯統一收斂為 **單一頂層路由權威（Single Routing Authority）**，支援：
1. 三大執行協定抽象 (`LOCAL`, `MCP`, `A2A`)。
2. 結構化任務規劃 (`Planner` 產出 `TaskPlan` 與 `SubTask`)。
3. 依賴導向循序調度 (`Orchestrator` 與 `ExecutionContext` 成果傳播)。
4. 確定性成果彙整 (`ResultAggregator` 判定全成功、全失敗或部分成功)。
5. 與既有 LangGraph、MCPManager、A2AClient、MemoryService 完整接線。

---

## Phase 6 Baseline
在進入 Phase 7 前，系統狀態如下：
- **Phase 1-4**: 完成 LangGraph 基礎 Agent 與多 MCP Servers 總管 (`MCPManager`)。
- **Phase 5**: 完成解耦的記憶體架構 (`MemoryService` 與 `SQLiteMemoryRepository`)。
- **Phase 6**: 完成標準 A2A 1.0.0 協定通訊 (`A2AClient`、`AgentDiscoveryService` 與 PCforge 菜單推薦對接)。
- **問題點**: LangGraph `agent_node` 同時處理 A2A 委派與 MCP 工具呼叫，缺乏多步驟任務規劃能力，且無法讓 A2A 產物自動傳播至 Memory 儲存庫。
- **測試基準**: 142 passed / 0 failed。

---

## Final Architecture
```text
User Request (CLI / LINE / Web API)
       ↓
LangGraph [agent_node]
       ↓
OrchestrationService (Application Boundary & Composition Root)
       ↓
Planner.plan(user_goal) ──► TaskPlan (1..N SubTasks with Dependency Graph)
       ↓
Orchestrator.execute_plan(plan)
       ↓
Router.route(subtask)
       ├─► LOCAL ──► LocalExecutor (MemoryAdapter, General QA, Reasoning)
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

## P7-01A Domain Models
- **檔案**: `app/orchestration/models.py`
- **核心模型**:
  - `ExecutionType` Enum: `LOCAL`, `MCP`, `A2A`
  - `ExecutionStatus` Enum: `PENDING`, `RUNNING`, `SUCCESS`, `FAILED`, `TIMEOUT`, `SKIPPED`
  - `AggregateStatus` Enum: `SUCCESS`, `PARTIAL_SUCCESS`, `FAILED`
  - `SubTask`: 包含 `task_id`, `execution_type`, `goal`, `target`, `parameters`, `depends_on`
  - `TaskPlan`: 包含 `plan_id`, `tasks`, `user_goal` (嚴格驗證重複 ID、自循環與不存在之依賴)
  - `ExecutionResult`: 包含執行耗時、狀態、成果與元數據
  - `AggregatedResult`: 成果彙整容器，`results` 作為唯一事實來源 (`@computed_field`)

---

## P7-01B Router / Orchestrator
- **檔案**: `app/orchestration/router.py`, `app/orchestration/orchestrator.py`, `app/orchestration/executors.py`
- **職責**:
  - `BaseExecutor`: 定義統一執行器協定 `execute(task, context) -> ExecutionResult`。
  - `LocalExecutor`: 管理本地 Python Handler 註冊與分派。
  - `A2AExecutor`: 對接 `AgentDiscoveryService` 與 `A2AClient`。
  - `Router`: 根據 `task.execution_type` 分派至對應 Executor。
  - `Orchestrator`: 協調單一與多任務生命週期。

---

## P7-02 Planner
- **檔案**: `app/orchestration/planner.py`
- **職責**:
  - `Planner`: 將自然語言 `user_goal` 轉換為結構化 `TaskPlan`。
  - `BasePlanningBackend`: 定義規劃後端介面。
  - `MockDeterministicPlanningBackend`: 無依賴確定性規劃後端，支援離線與測試。
  - `LangChainStructuredPlanningBackend`: 支援真實 LLM 的 `with_structured_output` 規劃。
  - `CapabilitySummary`: 動態向 Planner 提供系統已知 A2A、MCP 與 LOCAL 能力快照。

---

## P7-03 Sequential Execution
- **檔案**: `app/orchestration/orchestrator.py`, `app/orchestration/models.py`
- **機制**:
  - 支援 1..5 個子任務之循序拓撲執行。
  - `ExecutionContext(dependency_results)`：自動將上游任務的 `ExecutionResult` 傳遞給下游依賴任務。
  - **依賴故障安全略過**：若上游任務為 `FAILED` 或 `TIMEOUT`，下游依賴任務自動標記為 `SKIPPED`，絕不進入 Router。

---

## P7-04 MCP Integration
- **檔案**: `app/orchestration/executors.py`
- **機制**:
  - `MCPExecutor` 正式接入既有 `MCPManager`。
  - 將工具調用結果、逾時與異常標準化轉換為 `ExecutionResult`。
  - 完整支援 `own_server`, `sqlite_server`, `calendar_server` 多伺服器工具調度。

---

## P7-05 Memory Integration
- **檔案**: `app/orchestration/memory_adapter.py`
- **機制**:
  - `CANONICAL_MEMORY_CAPABILITY = "memory_store"`
  - `MemoryAdapter`：將 Phase 5 `MemoryService` 封裝為 Local Handler，支援直接寫入與依賴成果注入 (`dependency_results`)。
  - 實現「先 A2A 配單，再將結果寫入長期記憶」之端到端協同工作流。

---

## P7-06 Result Aggregation
- **檔案**: `app/orchestration/aggregator.py`
- **機制**:
  - `ResultAggregator.aggregate(plan, results) -> AggregatedResult`
  - 精準判斷 `SUCCESS` (全成功)、`PARTIAL_SUCCESS` (部分成功，部分失敗或略過) 與 `FAILED` (全失敗)。
  - 保留原始任務順序，並具備遺漏任務補齊為 `FAILED` 之健全防禦機制。

---

## P7-07 LangGraph Integration
- **檔案**: `app/orchestration/service.py`, `app/agent/graph.py`, `app/agent/nodes.py`
- **機制**:
  - `OrchestrationService` 作為 Application Boundary 與 Composition Root。
  - `create_agent_node` 支援全權委任 `OrchestrationService`，建立唯一頂層路由權威。
  - `create_orchestrated_graph` / `create_agent_graph(use_orchestration=True)` 提供一致的圖編譯入口。

---

## P7-08 E2E Verification
- **檔案**: `tests/test_p7_e2e_demo.py`
- **實測場景**:
  1. `test_p7_primary_demo_a2a_to_memory_workflow`: A2A (PCforge) ➔ LOCAL (Memory) 完整協作與檢索。
  2. `test_p7_local_reasoning_smoke`: LOCAL 推理與概念解析。
  3. `test_p7_mcp_read_only_tool_smoke`: MCP 唯讀安全工具 (`get_current_time`) 調用。
  4. `test_p7_failure_demo_a2a_offline_skips_memory`: 遠端離線 ➔ 依賴略過 ➔ 記憶零污染。
  5. `test_p7_partial_failure_demo`: A2A 成功但 Memory 異常 ➔ 成果保留且明確警示。

---

## Routing Authority
M.Ber 目前擁有 **唯一的頂層路由權威 (Single Routing Authority)**：
- 所有自然語言輸入均由 `Planner` 統一規劃為 `TaskPlan`。
- Phase 6 舊版 `A2ADelegator.match_and_delegate()` 與 Phase 1-4 頂層 Tool-calling 已完全退出生產調度路徑。

---

## A2A Flow
```text
User Intent ➔ Planner (ExecutionType.A2A) ➔ Router ➔ A2AExecutor ➔ AgentDiscoveryService (動態解析) ➔ A2AClient (JSON-RPC 2.0 SendMessage) ➔ Remote Peer Agent (PCforge) ➔ ExecutionResult(SUCCESS / FAILED)
```

---

## MCP Flow
```text
User Intent ➔ Planner (ExecutionType.MCP) ➔ Router ➔ MCPExecutor ➔ MCPManager (安全等級審查 & 跨 Server 路由) ➔ MCP StdIO Client ➔ ExecutionResult(SUCCESS / FAILED)
```

---

## Memory Flow
```text
Upstream Task (A2A / MCP) ➔ ExecutionResult ➔ ExecutionContext ➔ LocalExecutor (target="memory_store") ➔ MemoryAdapter ➔ MemoryService.remember() ➔ Persistent Storage (SQLite / InMemory)
```

---

## Failure Handling
- **上游失敗隔離**: 上游任務失敗時，下游依賴任務自動轉為 `SKIPPED`，避免產生連鎖無效呼叫或污染資料庫。
- **語意不隱瞞**: `ResultAggregator` 與 `synthesize_response` 誠實反映成功與失敗項目，絕不對使用者謊報已完成儲存。
- **無副作用合成**: 最終回覆合成層（Response Synthesizer）純粹解析 `AggregatedResult`，不發起任何新的工具調用或 A2A 通訊。

---

## Test Coverage
- **總測試數**: 168 項測試
- **通過率**: 100% (168 passed, 0 failed)
- **測試範圍**:
  - `test_smoke.py`: 基礎環境與設定
  - `test_agent_graph.py` & `test_langgraph_orchestration.py`: LangGraph 狀態圖與調度整合
  - `test_mcp_*.py` & `test_calendar_*.py`: MCP 工具、安全審查與伺服器總管
  - `test_memory_*.py`: 記憶模型、儲存庫與適配器
  - `test_a2a_*.py` & `test_pcforge_a2a.py`: A2A 協定、發現與委派
  - `test_orchestration_*.py` & `test_planner.py` & `test_orchestrator.py` & `test_aggregator.py`: 調度核心模組
  - `test_p7_e2e_demo.py`: 端到端全流程驗證

---

## Real Demo Result
### Primary Demo 執行範例：
- **使用者輸入**: `幫我配一台 40000 元遊戲電腦，然後幫我記住這套配置。`
- **規劃輸出**:
  - `Task 1`: A2A (`pc_recommendation`)
  - `Task 2`: LOCAL (`memory_store`, `depends_on=[Task 1]`)
- **執行結果**:
  - Task 1 成功取得 PCforge 40K 遊戲主機菜單 (AMD Ryzen 5 7500F + RTX 4060 Ti)。
  - Task 2 將菜單內容成功儲存至 `MemoryService`。
- **最終回覆**:
  ```text
  🤖 [A2A 遠端代理人: PCforge]
  任務狀態: completed
  已為您完成電腦組裝規劃（依據需求：'推薦一台 40000 元左右的遊戲主機菜單'）！

  📦 【pc_build_recommendation.md】
  # PCforge 40K 遊戲主機推薦菜單
  - CPU: AMD Ryzen 5 7500F ($5,200)
  - 主機板: B650M Gaming ($3,800)
  - 顯示卡: NVIDIA GeForce RTX 4060 Ti 8GB ($13,500)
  - 記憶體: DDR5-6000 16GB*2 ($3,200)
  - SSD: 1TB PCIe 4.0 NVMe M.2 ($2,200)
  - 電源供應器: 650W 80 Plus Gold ($2,600)
  - 機殼: 散熱透側機殼 ($1,800)
  - 總計預算: 約 $32,300 元 (預算餘裕 $7,700 可升級 2TB SSD 或 32GB RAM)

  💾 【記憶庫】: 已為您成功記住這項資訊。
  ```
- **記憶檢索驗證**: `memory_service.search("Ryzen")` 成功檢索出該筆記憶。

---

## Known Limitations
1. **靜態啟動快照**: Planner 的 `CapabilitySummary` 在初始化時建立快照，若於執行期間動態新增 MCP Server 或 AgentCard，需重啟或手動更新快照。
2. **Sequential DAG 限制**: 目前工作流僅支援循序依賴（Sequential Dependency Chain），尚未實作並行分支（Parallel Fan-out / Join）。
3. **確定性規劃後端**: 目前預設採用確定性規則後端 (`MockDeterministicPlanningBackend`)，LLM 自主規劃已建立架構介面，待 Phase 8 擴充。

---

## Phase 8 Handoff
### Phase 8 核心任務：
1. **Frontend & User Interface (Web / App / Chat UI)**：
   - 提供現代化、美觀的 Web 介面。
   - 透過簡潔的 API Gateway（HTTP / WebSocket / SSE）與後端 `OrchestrationService` 對接。
2. **Backend Entrypoint Stability**：
   - 前端無需理解 Planner、Router、A2A 或 MCP 的內部細節。
   - 前端僅需發送 `user_message`，後端回傳結構化對話與調度視覺化資料（可選展示 `TaskPlan` 與執行進度）。
