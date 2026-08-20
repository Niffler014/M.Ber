# Development Log: P6-03 Fix M.Ber CLI A2A Wiring

## 1. Meta Information

- **Date:** 2026-08-20
- **Phase:** Phase 6 — A2A (Agent2Agent) Protocol
- **Task ID:** P6-03
- **Task Title:** Fix M.Ber CLI A2A Wiring
- **Status:** COMPLETED

---

## 2. Goal

修復 M.Ber 終端機命令列介面（`app/cli.py`）之 A2A 子系統接線，使真實 CLI 在啟動時能透過既有的 `AgentDiscoveryService` 與 `A2ADelegator` 動態探索外部登記之 Peer Agents（例如 `http://localhost:8001` 的 PCforge），並將 `a2a_delegator` 注入至 LangGraph 狀態圖，實現終端機使用者提出電腦硬體需求時自動委派給 PCforge A2A Server。

---

## 3. Why the change was necessary (Root Cause)

### 根本原因分析
在先前的實作中，A2A 子系統各模組（`AgentDiscoveryService`、`A2AClient`、`A2ADelegator`）以及 LangGraph 核心圖建構函式 `create_agent_graph(mcp_manager=..., a2a_delegator=...)` 均已完成並通過單元測試。

然而在 `app/cli.py` 啟動進入點中：
1. 僅建立了 `mcp_manager = MCPManager()`。
2. 狀態圖僅以 `graph = create_agent_graph(mcp_manager=mcp_manager)` 建立。
3. `a2a_delegator` 未被初始化也未傳入 `create_agent_graph`。
4. 導致 `create_agent_node` 中的 A2A 委派分支判斷 `if a2a_delegator is not None:` 永遠為 False，CLI 始終落入內建模擬回覆，而無法將任務委派給真實運行的 PCforge。

---

## 4. Files Changed

| 檔案路徑 | 變更類型 | 變更說明 |
|---|---|---|
| `app/cli.py` | **Modified** | 引入 `AgentDiscoveryService` 與 `A2ADelegator`，於 CLI 啟動時批量探索外部 Peers，輸出連線狀態並將 `a2a_delegator` 注入狀態圖 |
| `tests/test_cli_a2a_wiring.py` | **Created** | 建立 CLI A2A 接線測試套件，涵蓋在線成功委派、離線安全降級與 CLI 啟動輸出驗證 |

---

## 5. Detailed Explanation & Architecture

### 5.1 Before / After 啟動與資料流比較

#### [Before]：
```
CLI startup
    ↓
MCPManager 初始化
    ↓
create_agent_graph(mcp_manager=mcp_manager)  [a2a_delegator 為 None]
    ↓
User 輸入「幫我推薦一台 40000 元的遊戲電腦」
    ↓
LangGraph Agent Node (無 a2a_delegator)
    ↓
Fallback 模擬回覆 (無任何外部委派)
```

#### [After]：
```
CLI startup
    ↓
1. MCPManager 初始化 (載入 config/mcp_servers.json)
    ↓
2. AgentDiscoveryService 初始化 (載入 config/a2a_agents.json)
    ↓
3. discover_configured_peers() ➔ 查詢 http://localhost:8001/.well-known/agent-card.json
    ↓
4. A2ADelegator(discovery_service=discovery_service)
    ↓
5. create_agent_graph(mcp_manager=mcp_manager, a2a_delegator=a2a_delegator)
    ↓
User 輸入「幫我推薦一台 40000 元的遊戲電腦」
    ↓
LangGraph Agent Node (檢查 a2a_delegator)
    ↓
a2a_delegator.match_and_delegate() ➔ 命中 PCforge 技能 (pc_recommendation)
    ↓
A2AClient 發送 JSON-RPC 2.0 SendMessage ➔ PCforge A2A Server
    ↓
接收 Task (COMPLETED) 與 Markdown 菜單產物 ➔ 呈現給終端使用者
```

### 5.2 離線降級容錯（Offline Fallback）設計
當 PCforge 或外部 Peer 處於未啟動（離線）狀態時：
- `discovery_service.discover_configured_peers()` 攔截網路異常（如 Connection Refused / Timeout），記錄警告但不拋出崩潰異常。
- CLI 終端機印出清晰狀態：
  ```
  ⚠️ [A2A Discovery]: PCforge unavailable
  ```
- CLI 繼續正常啟動，所有 MCP 工具、日曆、筆記以及標準對話仍能百分之百正常運作。

---

## 6. Important Code Concepts (新手教學)

### 1. 運行時依賴注入（Runtime Dependency Injection）
- 透過將 `a2a_delegator` 作為參數傳入 `create_agent_graph` 與 `create_agent_node`，Agent 不需要自己去尋找網路或建立 Client，而是由最外層的進入點（CLI 或 Webhook）統一配置並注入。這符合依賴反轉原則（Dependency Inversion Principle）。

### 2. 動態發現（Dynamic Discovery）與權威名片（Authoritative Card）
- 本地組態檔 `config/a2a_agents.json` 只記錄 Peer 在哪裡（WHERE），例如 `http://localhost:8001`。
- CLI 啟動時透過標準 A2A 路徑 `/.well-known/agent-card.json` 詢問該端點具有哪些技能（WHAT），並動態註冊至 `AgentDiscoveryService` 供調度使用。

---

## 7. Test Results

執行 pytest 測試結果：
```bash
uv run pytest
```
```
======================== 71 passed in 90.61s (0:01:30) ========================
```

所有 71 項測試皆已全數通過，包含：
- `tests/test_cli_a2a_wiring.py` (4 項新測試：在線委派、離線降級、CLI 輸出)
- `tests/test_pcforge_a2a.py` (6 項 A2A 整合測試)
- `tests/test_a2a_*.py` (A2A 協定、模型與發現測試)
- 其餘 LangGraph、MCP、Calendar、Memory 等所有測試無任何 regression。

---

## 8. Manual Demo Command

啟動 PCforge A2A Server（在另一個終端機）：
```bash
# 在 PCforge 專案目錄下啟動
uv run python -m app.main
```

啟動 M.Ber CLI：
```bash
uv run python -m app.cli
```

測試指令範例：
```
👤 使用者: 幫我推薦一台 40000 元左右的遊戲電腦
```
預期輸出：
```
🤝 [A2A Discovery]: discovered agents: ['PCforge']
...
🤖 [A2A 遠端代理人: PCforge (技能: PC Hardware & Build Recommendation)]
任務狀態: completed
已為您規劃符合 40,000 元預算的最佳遊戲電腦配置。
📦 【pc_build_recommendation.md】
...
```

---

## 9. Next Step

- 進行實機 A2A 跨代理人協同測試。
- 準備 Phase 7 跨代理人多工排程與更進階之 LLM 語意意圖路由。
