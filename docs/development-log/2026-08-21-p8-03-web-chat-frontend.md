# Development Log: Phase 8 P8-03 — Web Chat Frontend

## 1. 基本資訊
- **日期 (Date)**：2026-08-21
- **階段 (Phase)**：Phase 8 — Web API & Interactive Demo UI (P8-03)
- **目標 (Goal)**：建立獨立之 React + Vite + TypeScript 前端 Web 應用程式（`frontend/`），實現現代化對話介面、即時健康狀態檢測、SSE 串流解析，以及可視化 Execution Trace 執行進度面板。

---

## 2. 為什麼需要這項變更 (Why)
在 P8-01 與 P8-02 中，M.Ber 後端已具備標準 HTTP API 與 Server-Sent Events 即時事件串流能力（`POST /api/chat/stream`）。
為了讓使用者能直觀、即時地與 M.Ber 互動並觀測多代理人（A2A）、工具（MCP）、記憶庫（Memory）與規劃器（Planner）的協同運作流程，我們需要一個美觀、高效且安全的 Web 使用者介面。

---

## 3. 前端技術堆疊與目錄結構 (Frontend Stack & Folder Structure)

### (1) 技術選型
- **框架與建置工具**：React 18 + Vite 5 + TypeScript 5
- **樣式系統**：Vanilla CSS（具備現代深色科技風格、變數系統、流暢轉場與響應式排版）
- **Markdown 渲染**：`react-markdown`（安全渲染助理回覆之清單、表格、程式碼區塊）
- **圖示庫**：`lucide-react`（輕量、高一致性向量圖示）
- **測試框架**：Vitest + `@testing-library/react` + `jsdom`

### (2) 專案結構
```text
frontend/
├── package.json               # 前端套件定義與執行腳本 (dev / build / test)
├── tsconfig.json              # TypeScript 編譯器配置
├── tsconfig.node.json
├── vite.config.ts             # Vite 與 Vitest 設定
├── index.html                 # Web HTML 進入點
├── .env.example               # 前端環境變數範本 (VITE_API_BASE_URL)
├── src/
│   ├── main.tsx               # React 根節點渲染
│   ├── App.tsx                # 應用主架構、狀態管理與串流調度
│   ├── index.css              # 主題變數、對話氣泡、軌跡面板與響應式樣式
│   ├── vite-env.d.ts          # Vite 環境型別聲明
│   ├── api/
│   │   ├── config.ts          # API Base URL 集中設定
│   │   ├── types.ts           # 前端公用 DTO (HealthResponse, ChatResponse, TraceEvent 等)
│   │   ├── sseParser.ts       # 健全的 SSE 串流解析器 (支援跨 Chunk、多事件分塊)
│   │   └── client.ts          # HTTP 與 Fetch ReadableStream API 客戶端
│   ├── components/
│   │   ├── Header.tsx         # 頂部導航列 (品牌名稱、後端 Online/Offline 即時狀態)
│   │   ├── ChatPanel.tsx      # 對話區域主容器
│   │   ├── MessageList.tsx    # 訊息列表 (含初始 4 個示範 Prompt 卡片與自動滾動)
│   │   ├── MessageBubble.tsx  # 單一對話氣泡 (支援 Markdown、複製、Partial Success 與 Error 標籤)
│   │   ├── ChatComposer.tsx   # 輸入文字框 (Enter 送出、Shift+Enter 換行、自動伸縮)
│   │   ├── ExecutionTracePanel.tsx # 右側即時執行軌跡面板 (LIVE 動畫、整體狀態標籤)
│   │   └── TraceItem.tsx      # 單筆調度事件項目 (圖示、親切文字、耗時與目標標籤)
│   └── types/
│       └── chat.ts            # UI ChatMessage 模型
└── tests/
    ├── setup.ts               # 測試環境初始化與 JSDOM 補丁
    ├── sseParser.test.ts      # SSE 解析器單元測試 (7 項)
    └── App.test.tsx           # 前端主元件整合測試 (7 項)
```

---

## 4. 核心實作重點 (Key Implementation Details)

### (1) 健全的 SSE 串流解析器 (`src/api/sseParser.ts`)
- 由於網路傳輸的 TCP / HTTP Chunk 邊界不一定等於 SSE 格式的換行邊界，若直接假設每次 `reader.read()` 為單一事件將導致封包毀損。
- `SSEParser` 維護內部字串緩衝區，精確尋找 `\n\n` 事件邊界，能無縫處理：
  1. 跨 Chunk 切割的事件（Split across chunks）
  2. 單一 Chunk 包含多筆事件（Multiple events in one chunk）
  3. Windows CRLF (`\r\n`) 換行相容
  4. 忽略以 `:` 開頭的心跳註解行

### (2) 執行軌跡可視化映射 (`src/components/TraceItem.tsx`)
- 避免將後端技術欄位（如 `task_started`、`execution_type=a2a`、`target=pc_recommendation`）原始字串直接暴露給一般使用者。
- 將事件即時轉譯為易讀之語言與狀態圖示：
  - `planning_started` ➔ 🧠 **Planning Analysis**
  - `plan_created` ➔ 🧠 **Plan Created (2 tasks)**
  - `task_started` (A2A PCforge) ➔ 🌐 **PCforge Working**
  - `task_completed` (A2A PCforge) ➔ 🌐 **PCforge Complete** (顯示 `1.20s`)
  - `task_started` (Memory) ➔ 💾 **Saving Memory**
  - `task_completed` (Memory) ➔ 💾 **Memory Saved**
  - `aggregation_completed` ➔ ✨ **Aggregating Results**
  - `response_ready` ➔ ✨ **Synthesizing Response**

### (3) 多元狀態與部分成功 (Partial Success) 處理
- 當後端調度遭遇部分依賴失敗時（如 A2A 成功但 Memory 存入鎖定失敗，整體狀態為 `partial_success`）：
  - 助理回覆維持正常呈現，並於標題附帶 `⚠️ Partial Success` 警示徽章。
  - 右側 Execution Trace 面板明確標示成功與失敗/略過之子任務，避免使用者誤以為整筆請求完全失敗。

### (4) 鍵盤操作與並行限制
- 支援 `Enter` 發送訊息，`Shift + Enter` 換行。
- 當處於串流狀態（`isStreaming = true`）時，鎖定輸入框與送出按鈕，確保每個對話階段一次僅執行一筆請求，避免狀態競態。

---

## 5. 測試驗證 (Test Results)

### (1) 前端測試 (Vitest)
```powershell
npm run test
```
```text
✓ tests/sseParser.test.ts (7 tests) 10ms
✓ tests/App.test.tsx (7 tests) 342ms

Test Files  2 passed (2)
     Tests  14 passed (14)
  Duration  4.65s
```

### (2) 前端生產建置 (Production Build)
```powershell
npm run build
```
```text
✓ 1748 modules transformed.
dist/index.html                   0.78 kB │ gzip:  0.44 kB
dist/assets/index-VBSgCIWr.css   12.81 kB │ gzip:  3.09 kB
dist/assets/index-DKHKl-tJ.js   287.75 kB │ gzip: 90.17 kB
✓ built in 11.84s
```

### (3) 後端回歸測試 (Backend Pytest)
```powershell
uv run pytest
```
```text
======================= 194 passed in 120.70s (0:02:00) =======================
0 failed
```

---

## 6. 初學者解說 (Beginner Explanation)
> **什麼是前端與後端的 SSE 串流通訊？**
> 過去的傳統網頁就像寄信：你寄出一封信（HTTP POST），必須等對方寫完整封回信寄回來，你才能一次看到所有內容。
> 
> 現在的 M.Ber Web UI 就像打開了對講機（Server-Sent Events 串流）：
> 1. 當你在聊天框輸入「幫我配電腦並記住」按下發送。
> 2. 後端調度大腦開始運轉，每完成一個思考動作，就立刻透過對講機發送一句進度廣播（Trace Event）。
> 3. 前端瀏覽器利用 `ReadableStream` 即時接收廣播，右側的「Execution Trace」面板立刻亮起打勾動畫與耗時時間。
> 4. 最後收到「Final」訊息時，左側聊天氣泡瞬間排版呈現完整的 Markdown 建議菜單！

---

## 7. 下一步 (Next Step)
- 進入 **P8-04 — MCP Activity & Runtime Inspector**：
  - 開發 MCP 專屬活動檢視面板與工具清單偵測。
