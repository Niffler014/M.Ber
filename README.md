# M.Ber — Personal AI Agent Platform

> **Project Status:** Phase 7 Multi-Agent & Tool Orchestration Layer Completed  
> **Next Phase:** Phase 8 Frontend / User Interface & API Gateway  
> **Version:** 0.7.0  
> **Primary Language:** Python (>= 3.10)  
> **Orchestration Runtime:** LangGraph + M.Ber Orchestration Engine  
> **Protocol Standard:** MCP (Tools) & A2A 1.0 (Agent Interoperability)

---

## 1. Overview

**M.Ber** 是一個以個人使用為核心的 Personal AI Agent 平台。

M.Ber 不僅僅是一個對話機器人，而是具備長期記憶、任務規劃、工具調用（Model Context Protocol）以及多代理人協作（Agent2Agent Protocol）能力的個人 AI 助理。

本專案的核心目標是：**在建構現代 AI Agent 系統的同時，透過可解釋的漸進式開發，讓開發者深刻理解每一行程式碼與背後架構原理。**

---

## 2. Core Architecture (系統核心架構)

在 **Phase 7** 中，M.Ber 正式建立了單一路由權威（Single Routing Authority）調度中樞架構：

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

### 核心能力 (Capabilities)
- **單一頂層路由權威 (Single Routing Authority)**：所有意圖由 Planner 統一規劃，徹底消除雙重路由與邏輯散落問題。
- **三協定統一調度 (LOCAL / MCP / A2A)**：標準化任務模型 `SubTask` 與結果模型 `ExecutionResult`，跨協定解耦。
- **多步驟循序與依賴傳播 (Sequential Multi-Task & Dependencies)**：支援工作流上游輸出自動作為下游輸入（如：外部代理人配單成果自動注入長期記憶庫）。
- **故障隔離與部分失敗處理 (Partial Failure Handling)**：上游任務失敗時自動跳過下游依賴任務（`SKIPPED`），防止資料庫污染；同時保留部分成功產物。

---

## 3. Primary Demo (真實端到端示範)

### 執行範例：跨代理人循序工作流
使用者輸入：
```text
幫我配一台 40000 元遊戲電腦，然後幫我記住這套配置。
```

系統執行軌跡：
1. **Planner** 規劃兩步任務：
   - `Task 1 (A2A)`: 委派 PCforge 專家提供 40K 遊戲主機組裝菜單。
   - `Task 2 (LOCAL)`: 將 Task 1 之菜單寫入 M.Ber 長期記憶庫（`memory_store`，`depends_on=Task 1`）。
2. **Orchestrator & Router** 依序調度：
   - 透過 `A2AExecutor` 連線至 PCforge，取得 Ryzen 5 7500F + RTX 4060 Ti 配置。
   - 透過 `LocalExecutor` 與 `MemoryAdapter` 將配單成果持久化寫入 `MemoryService`。
3. **ResultAggregator** 彙整整體狀態為 `SUCCESS`。
4. **Final Response** 產出結構化且友善的回覆，並可隨時以 `MemoryService.search("Ryzen")` 檢索回憶。

---

## 4. Project Structure (專案目錄結構)

```text
.
├── .env.example             # 環境變數範本（API Keys、LINE Webhook 金鑰等）
├── .gitignore               # Git 忽略檔案清單（快取、私鑰、虛擬環境、本地 DB 等）
├── AGENTS.md                # AI 開發指引與專案核心守則
├── README.md                # 專案介紹與使用說明
├── pyproject.toml           # Python 專案元數據、依賴套件與 pytest 配置
├── app/                     # M.Ber 應用主程式模組
│   ├── __init__.py
│   ├── cli.py               # 終端機即時互動介面 (已接入 Orchestration Engine)
│   ├── a2a/                 # A2A 代理人互操作模組 (AgentCard, Discovery, Client)
│   ├── agent/               # LangGraph 狀態圖、節點與統一調度橋樑
│   ├── interfaces/          # 外部通訊轉接站 (LINE Webhook Gateway 等)
│   ├── mcp/                 # MCP 客戶端連線器與多伺服器總管 (MCPManager)
│   └── orchestration/       # Phase 7 調度核心模組 (Models, Router, Orchestrator, Planner, Executors, Aggregator, Service)
├── config/                  # 外部 MCP / A2A 伺服器配置 (mcp_servers.json, a2a_agents.json)
├── data/                    # 本地資料庫目錄 (calendar.db、memory.db 等)
├── docs/                    # 專案文件與架構規格
│   ├── PROJECT_SPEC.md      # 專案總體規格書
│   ├── architecture/        # 架構與協定版本紀錄 (protocol-versions.md)
│   └── development-log/     # 每次修改之開發日誌
├── mcp_server/              # 本地與第三方風格 MCP 伺服器模組
│   ├── my_mcp_server.py     # 自有時間與回音伺服器 (Phase 2)
│   └── third_party/         # SQLite 筆記與行事曆伺服器 (Phase 3, Phase 4)
├── memory/                  # 記憶管理子系統 (Phase 5 完成)
├── services/                # 外部服務整合模組
└── tests/                   # 自動化測試套件 (168 項全數通過)
```

---

## 5. Quickstart & Testing (快速開始與測試)

### 環境需求
* Python >= 3.10
* uv (推薦)
* Node.js >= 18 (前端 Web UI)

### 執行後端測試
本專案使用 `pytest` 作為後端測試執行器：

```powershell
uv run pytest
```

### 啟動後端 Web API 伺服器 (FastAPI)
```powershell
uv run uvicorn app.interfaces.web.gateway:app --host 127.0.0.1 --port 8000 --reload
```

### 啟動前端 Web Chat UI (React + Vite)
```powershell
cd frontend
npm install
npm run dev
```
瀏覽器開啟 `http://localhost:5173` 即可進行互動式對話與調度軌跡即時觀測。

### 啟動 CLI 終端機對話
```powershell
uv run python -m app.cli
```

---

## 6. Phase Roadmap (開發路線圖)

- [x] **Phase 0: Foundation** (已完成)
- [x] **Phase 1: Basic LangGraph Agent** (已完成)
- [x] **Phase 2: Own MCP Server** (已完成)
- [x] **Phase 3: Third-party MCP Integration** (已完成)
- [x] **Phase 4: Calendar Integration** (已完成)
- [x] **Phase 5: Memory Subsystem** (已完成)
- [x] **Phase 6: A2A (Agent2Agent) Protocol** (已完成)
- [x] **Phase 7: Multi-Agent & Tool Orchestration** (已完成)
- [ ] **Phase 8: Web API & Interactive Demo UI** (進行中)
  - [x] P8-01: Backend HTTP API & Gateway
  - [x] P8-02: Execution Trace Collection & SSE Streaming
  - [x] P8-03: Web Chat Frontend (React + Vite + SSE Trace UI)
  - [x] P8-04: MCP Activity & Runtime Inspector
  - [ ] P8-05: Multi-Channel Expansion (LINE Notification)
  - [ ] P8-06: Production Build & Phase Closure
- [ ] **Phase 9: Observability, Evaluation & A2A Server Export**
- [ ] **Phase 10: Production Hardening**

