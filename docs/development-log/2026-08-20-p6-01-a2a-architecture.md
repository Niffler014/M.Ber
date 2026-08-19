# Development Log: P6-01 Minimal A2A 1.0 Interoperable Subset Architecture & Implementation

## 1. Meta Information

- **Date:** 2026-08-20
- **Phase:** Phase 6 — A2A (Agent2Agent) Protocol
- **Task ID:** P6-01
- **Task Title:** Minimal A2A 1.0 Interoperable Subset Architecture, Models & JSON-RPC Client Implementation
- **Status:** COMPLETED

---

## 2. Goal & Scope Definition (Minimal A2A 1.0 Subset)

為 JARVIS 建立符合官方 **A2A 1.0.0 規範** 的最小可行互操作子集（Minimal A2A 1.0 Interoperable Subset），聚焦於代理人能力聲明、發現與基礎任務交涉。

### 2.1 本階段實作範圍 (In-Scope)
1. **Agent Card (`AgentCard`)**：官方標準代理人數位名片（`name`, `description`, `url`, `version`, `capabilities`, `skills`, `default_input_modes`, `default_output_modes`, `security_schemes`, `security`）。
2. **Agent Skill (`AgentSkill`)**：專業能力宣告（`id`, `name`, `description`, `tags`, `examples`, `input_modes`, `output_modes`）。
3. **Agent Card 發現 (`AgentDiscoveryService`)**：支援自 `config/a2a_agents.json` 載入已知 Peer Agents，並提供標準 `/.well-known/agent-card.json` 端點路徑合成。
4. **多段式訊息 (`Message` & `TextPart`)**：支援結構化多段式對話訊息傳遞與純文字提取。
5. **任務與生命週期 (`Task` & `TaskStatus`)**：支援狀態化任務單元與 6 大官方生命週期狀態（`submitted`, `working`, `input_required`, `completed`, `failed`, `canceled`）。
6. **成果產物 (`Artifact`)**：任務不可變產出結構。
7. **JSON-RPC 2.0 綁定與客戶端 (`A2AClient`)**：基於 JSON-RPC 2.0 實作 `SendMessage`、`GetTask`、`CancelTask` 與結構化錯誤處理（`A2AClientError`）。

### 2.2 延後實作項目 (Deferred / Out-of-Scope)
- ❌ 即時串流（SSE / SendStreamingMessage）
- ❌ Webhook 推播通知（Push Notifications）
- ❌ 集中式分散式代理人註冊中心（Service Mesh / Registry）
- ❌ OAuth2 / 授權伺服器架構實作
- ❌ 複雜多代理人分散式編排（Multi-Agent Orchestration）

---

## 3. MCP vs A2A: 協定與職責邊界定義

| 評估維度 | Model Context Protocol (MCP) | Agent-to-Agent Protocol (A2A) |
| :--- | :--- | :--- |
| **通訊對象** | Agent $\leftrightarrow$ Tool / Resource / Server | Agent A $\leftrightarrow$ Agent B (Peer-to-Peer 代理人間協作) |
| **核心語意** | 「幫我執行這個函式 / 查這筆資料」 (RPC / Deterministic) | 「請你這個專家幫我規劃並完成一項子任務」 (Delegation / Collaboration) |
| **自主性 (Autonomy)** | 工具無自主思考能力，僅被動接收參數並回傳結果 | 雙方皆具備獨立大腦（LLM）、私有狀態與目標決策能力 |
| **能力宣告** | Tools Schema (JSON Schema: 名稱、參數說明) | Agent Card (包含身份、Skills、Capabilities、Security) |
| **通訊模型** | Stdio / SSE / JSON-RPC 2.0 (Request / Response) | HTTP POST / JSON-RPC 2.0 (`SendMessage`, `GetTask`, `CancelTask`) |
| **狀態可見性** | Client 掌握全部上下文，Tool 無私有認知狀態 | 彼此無法看見對方的內部私有 State、Prompt 或 Memory |

> **記憶子系統整合原則**：
> 任何 A2A 交互成果沉澱為記憶，皆必須遵守：
> $$\text{A2A Subsystem} \longrightarrow \text{Application / Agent Layer} \longrightarrow \text{MemoryService} \longrightarrow \text{MemoryRepository}$$
> 絕不允許 A2A 直接讀寫底層 SQLite 資料庫。

---

## 4. 系統架構分層圖

```text
                               ┌────────────────────────────────┐
                               │       User / Inbound (LINE)    │
                               └───────────────┬────────────────┘
                                               │
                                               ▼
                               ┌────────────────────────────────┐
                               │    JARVIS Orchestrator Core    │
                               │      (app.agent / LangGraph)   │
                               └───────┬────────────────┬───────┘
                                       │                │
                      ┌────────────────┘                └────────────────┐
                      │ (Tool Invocation)                                │ (Agent Delegation)
                      ▼                                                  ▼
     ┌─────────────────────────────────┐                ┌─────────────────────────────────┐
     │          MCP Subsystem          │                │          A2A Subsystem          │
     │            (app.mcp)            │                │            (app.a2a)            │
     │  - MCPManager (Multi-Server)    │                │  - models.py (A2A 1.0 Schemas)  │
     │  - MCPStdioClient (RPC)         │                │  - discovery.py (Discovery Svc) │
     │  - Tools: Time, Notes, Calendar │                │  - client.py (JSON-RPC Client)  │
     └─────────────────────────────────┘                └────────────────┬────────────────┘
                                                                         │
                                                                         ▼ (JSON-RPC 2.0 / HTTP)
                                                        ┌─────────────────────────────────┐
                                                        │       Remote Peer Agents        │
                                                        │   (ResearchAgent, CoderAgent)   │
                                                        └─────────────────────────────────┘
                                       │
                                       ▼ (透過領域門面進行記憶存取)
                       ┌───────────────────────────────┐
                       │         MemoryService         │
                       │       (memory.service)        │
                       └───────────────┬───────────────┘
                                       │
                                       ▼
                       ┌───────────────────────────────┐
                       │       MemoryRepository        │
                       │      (memory.repository)      │
                       └───────┬───────────────┬───────┘
                               ▼               ▼
                     InMemoryMemoryRepo  SQLiteMemoryRepo
```

---

## 5. Files Changed & Created

| File | Status | Description |
| :--- | :--- | :--- |
| `app/a2a/models.py` | **Created** | A2A 1.0 領域資料模型（`AgentCard`, `AgentSkill`, `Task`, `Message`, `TextPart`, `Artifact`, `JSONRPCRequest`, `JSONRPCResponse`） |
| `app/a2a/discovery.py` | **Created** | 代理人發現服務（`AgentDiscoveryService`，解析 `config/a2a_agents.json` 與技能檢索） |
| `app/a2a/client.py` | **Created** | A2A JSON-RPC 2.0 客戶端（`A2AClient`，實作 `SendMessage`, `GetTask`, `CancelTask`） |
| `app/a2a/__init__.py` | **Created** | A2A 套件初始化與核心 API 匯出 |
| `config/a2a_agents.json` | **Created** | 外部 Peer Agents（ResearchAgent, CoderAgent）組態設定檔 |
| `tests/test_a2a_card.py` | **Created** | Agent Card 與領域模型驗證與 JSON Roundtrip 測試 |
| `tests/test_a2a_discovery.py` | **Created** | Discovery 服務組態載入與技能探索單元測試 |
| `tests/test_a2a_client.py` | **Created** | JSON-RPC 2.0 通訊、Task 生命週期與錯誤處理單元測試 |
| `docs/architecture/protocol-versions.md` | **Modified** | 記錄 A2A 1.0.0 協定規格與配置 |

---

## 6. Test Results

執行指令：
```powershell
$env:PATH = "E:\code\ive\M.Ber\.venv\Scripts;" + $env:PATH; pytest
```

輸出結果：
```text
============================= test session starts =============================
platform win32 -- Python 3.14.4, pytest-9.1.1, pluggy-1.6.0
rootdir: E:\code\ive\M.Ber
configfile: pyproject.toml
testpaths: tests

tests/test_a2a_card.py (6 passed)
tests/test_a2a_client.py (6 passed)
tests/test_a2a_discovery.py (4 passed)
tests/test_agent_graph.py (6 passed)
tests/test_calendar_integration.py (3 passed)
tests/test_calendar_server.py (2 passed)
tests/test_line_gateway.py (5 passed)
tests/test_mcp_integration.py (2 passed)
tests/test_mcp_manager.py (3 passed)
tests/test_mcp_server.py (3 passed)
tests/test_mcp_third_party.py (3 passed)
tests/test_memory_contract.py (6 passed)
tests/test_memory_sqlite.py (3 passed)
tests/test_smoke.py (7 passed)

======================== 59 passed ========================
```
**結果：59/59 測試全數通過（100% Pass，新增 16 項 A2A 測試，既有 43 項測試無任何回歸）。**

---

## 7. 新手白話文教學 (Beginner Explanation)

> **💡 什麼是 JSON-RPC 2.0 與 Agent-to-Agent 通訊？**
> 
> 1. **名片（Agent Card）**：當 JARVIS 想要找幫手時，先翻開通訊錄（`config/a2a_agents.json`），找到「ResearchAgent」這張名片，上面寫著它的強項是「深度研究（deep_research）」以及通訊地址（`https://research-agent.local/v1/a2a`）。
> 2. **任務信封（JSON-RPC 2.0 Envelope）**：JARVIS 不能直接把腦中的程式碼丟過去，而是要把要求裝進一個標準規格的信封裡：
>    - 寫上標題（`method: "SendMessage"`）
>    - 裝入任務細節（`message: { role: "user", parts: [{ type: "text", text: "請研究 2026 年 AI 協定" }] }`）
>    - 貼上信件序號（`id: "req-001"`）
> 3. **工作單回條（Task）**：對方收到後，回傳一張標準工作單（`Task`），上面清楚標示任務進度（`state: "completed"`）以及研究成果（`artifacts: [report.md]`）。
> 
> 透過這種統一的「名片」與「信封」格式，不管全世界的 AI Agent 是用 Python、Node.js 還是 Go 寫的，都能無縫跨語言協作！
