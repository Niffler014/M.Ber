# Development Log: P6-02 PCforge A2A Client Integration

## 1. Meta Information

- **Date:** 2026-08-20
- **Phase:** Phase 6 — A2A (Agent2Agent) Protocol
- **Task ID:** P6-02
- **Task Title:** PCforge A2A Client Integration & Dynamic Agent Card Discovery
- **Status:** COMPLETED

---

## 2. Background & Integration Rationale

M.Ber 是一個個人智慧助理平台（JARVIS Orchestrator）。在真實世界場景中，單一代理人無法也不應該內建所有專業領域的龐大邏輯。
PCforge 是一個專注於電腦硬體配置、零組件相容性檢測與組裝菜單推薦的獨立 AI 專案。

透過 **A2A (Agent-to-Agent Protocol 1.0.0)** 標準協定，M.Ber 能夠以 **A2A Client** 的身份，將使用者的電腦硬體組裝需求委派（Delegate）給獨立運行的 **PCforge A2A Server**，取得專業組裝建議與菜單產物（Artifacts），並統整回覆給使用者。

### 為什麼兩個儲存庫（Repository）必須保持完全獨立？
1. **職責分離（Separation of Concerns）**：M.Ber 負責個人日程、筆記與總體協調；PCforge 負責硬體資料庫、算力評估與菜單生成。
2. **無程式碼依賴（Zero Code Coupling）**：M.Ber 不匯入任何 PCforge 原始碼（禁止 `import pcforge`），彼此互不認識私有 State 與內部實作。
3. **協定標準化（Standard Protocol Boundary）**：雙方僅透過標準的 A2A 1.0.0 JSON-RPC 2.0 訊息信封與標準 Agent Card 溝通，未來 PCforge 若以 Go 或 Rust 重構，M.Ber 亦無需修改任何一行程式碼。

---

## 3. 系統角色與職責分工 (Roles & Responsibilities)

```
┌─────────────────────────────────────────────────────────────┐
│                       M.Ber (A2A Client)                    │
│                                                             │
│  - 讀取組態檔登記之端點位置 (WHERE: http://localhost:8001)  │
│  - 動態獲取遠端 Agent Card (/.well-known/agent-card.json)   │
│  - 根據宣稱之 Skills 進行確定性能力匹配 (WHAT)              │
│  - 封裝 JSON-RPC 2.0 SendMessage 請求並發送至端點           │
│  - 解析 Task / Message 回應與 Artifacts 產物                │
│  - 整合結果呈現給使用者                                     │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               │ A2A 1.0 / JSON-RPC 2.0 (HTTP POST)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 PCforge (A2A Server / Adapter)              │
│                     (獨立專案，非本專案範圍)                │
│                                                             │
│  - 於 /.well-known/agent-card.json 伺服權威 Agent Card      │
│  - 接收 JSON-RPC 2.0 呼叫 (SendMessage, GetTask)            │
│  - 驅動 PCforge 內部 Agent 規劃硬體菜單                     │
│  - 回傳狀態化 Task (COMPLETED) 及 Markdown 產物 (Artifacts)  │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. 核心架構邊界與發現語意 (WHERE vs. WHAT)

### 4.1 WHERE vs. WHAT 發現原則
- **M.Ber 組態檔 (`config/a2a_agents.json`)**：僅記錄 external peer 的位置（WHERE），例如：
  ```json
  {
    "peers": [
      {
        "name": "PCforge",
        "url": "http://localhost:8001"
      }
    ],
    "agents": [ ... ]
  }
  ```
  M.Ber **絕不** 在本地組態中重複定義 PCforge 的技能清單、描述或版本，確保單一真實來源（Single Source of Truth）。

- **權威 Agent Card (WHAT)**：M.Ber 透過 `AgentDiscoveryService.discover_peer(url)` 訪問 `http://localhost:8001/.well-known/agent-card.json` 動態取得並校驗 PCforge 聲明的技能（`pc_recommendation`）。

### 4.2 確定性技能調度與隔離設計 (`A2ADelegator`)
- 不在 `nodes.py` 中散落寫死「組裝」、「菜單」等業務邏輯。
- 由 `app/a2a/delegator.py` 中的 `A2ADelegator` 獨立封裝：
  1. 檢查輸入是否命中已註冊 Agent 的宣告技能（Tags、Examples、Skill ID）。
  2. 調用 `A2AClient.send_message()` 透過標準信封交涉。
  3. 解析 `Task` 狀態與 `Artifact`。
  此設計為 Phase 6 確定性 MVP，未來可平滑升級為 LLM-based Intent Router 而不衝擊 A2A 協定底層。

---

## 5. 檔案變更清單 (Files Changed & Created)

| 檔案 | 狀態 | 說明 |
| :--- | :--- | :--- |
| `config/a2a_agents.json` | **Modified** | 新增 `peers` 外部端點宣告（僅記錄 URL 位置，不寫死 Agent Card） |
| `app/a2a/discovery.py` | **Modified** | 新增 `fetch_agent_card`、`discover_peer`、`discover_configured_peers` 與確定性技能匹配 `find_agent_for_query` |
| `app/a2a/delegator.py` | **Created** | 獨立建立 `A2ADelegator` 代理任務委派調度器，保持 Agent 節點乾淨 |
| `app/a2a/__init__.py` | **Modified** | 匯出 `A2ADelegator` 與 `CardTransportHandler` |
| `app/agent/nodes.py` | **Modified** | `create_agent_node` 支援注入 `a2a_delegator`，乾淨分支委派 |
| `app/agent/graph.py` | **Modified** | `create_agent_graph` 支援注入 `a2a_delegator` |
| `tests/test_pcforge_a2a.py` | **Created** | 涵蓋動態探索、JSON-RPC 封裝、技能匹配與端到端模擬整合測試（6 項測試） |
| `docs/development-log/2026-08-20-p6-02-pcforge-a2a-client.md` | **Created** | 本開發日誌 |

---

## 6. 本地整合與手動連線指引 (Local Integration Procedure)

當 PCforge 獨立實作完成其 A2A Server 後，依照以下步驟進行連線：

1. **啟動 PCforge A2A Server**：
   - 確保 PCforge 伺服器啟動於本機（例如 `http://localhost:8001`）。
   - 確保訪問 `http://localhost:8001/.well-known/agent-card.json` 可回傳 PCforge 的 Agent Card JSON。

2. **確認 M.Ber 設定檔**：
   - 確認 `config/a2a_agents.json` 中的 `peers` 指向 PCforge 的實際監聽端點：
     ```json
     {
       "peers": [
         {
           "name": "PCforge",
           "url": "http://localhost:8001"
         }
       ]
     }
     ```

3. **啟動 M.Ber 對話互動**：
   - 執行命令列介面：
     ```powershell
     $env:PATH = "E:\code\ive\M.Ber\.venv\Scripts;" + $env:PATH; python -m app.cli
     ```
   - 輸入：「推薦一台 40000 元左右的遊戲主機菜單」
   - M.Ber 將自動探索 PCforge、發送 A2A 委派請求並顯示 PCforge 生成的菜單。

---

## 7. PCforge 側所需實作項目 (What PCforge Must Implement)

PCforge 側只需實作 A2A Server/Adapter，滿足以下契約：
1. **Agent Card Endpoint**：
   - 路由：`GET /.well-known/agent-card.json`
   - 回傳包含 `name: "PCforge"`、`skills: [{"id": "pc_recommendation", ...}]` 的合法 AgentCard JSON。
2. **JSON-RPC 2.0 Endpoint**：
   - 路由：`POST /v1/a2a`（或 Agent Card 中宣告之 `url`）
   - 支援方法：`SendMessage`
   - 回傳包含 `id`、`status: { state: "completed", message: ... }` 及 `artifacts: [ { name: "pc_build.md", ... } ]` 的 JSON-RPC 2.0 Response。

---

## 8. 測試驗證結果 (Test Results)

執行完整測試套件：
```powershell
$env:PATH = "E:\code\ive\M.Ber\.venv\Scripts;" + $env:PATH; pytest
```

- 既有測試：全數通過（無任何回歸）
- 新增測試：`tests/test_pcforge_a2a.py` 6/6 通過
- **總計：67 passed（100% 通過率）**

---

## 9. 新手白話文教學 (Beginner Explanation)

> **💡 為什麼要分 WHERE 和 WHAT？**
> 
> 想像你的通訊錄（`config/a2a_agents.json`）：
> - 通訊錄只寫了「小明的電話號碼是 0912-345-678」（這是 **WHERE**，位置）。
> - 小明到底擅長修電腦還是煮咖啡？這是小明見面時遞給你的名片（`Agent Card`）上寫的（這是 **WHAT**，能力）。
> 
> 如果我們把「小明會修電腦」直接寫死在你的通訊錄裡，哪天小明轉行去當廚師了，你的通訊錄就變成了錯誤資訊！
> 
> 因此，最優雅的做法是：
> 1. M.Ber 拿起電話撥給小明（`fetch_agent_card`）。
> 2. 小明把最新的數位名片傳過來。
> 3. M.Ber 看著名片確認「小明現在依然擅長修電腦」，才把修電腦的任務交給他（`SendMessage`）。
> 
> 這就是現代開放代理人網路（Open Agent Network）中「動態探索」的精髓！
