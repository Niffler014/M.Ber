# Development Log: P8-03.5 Production Planner A2A Routing Fix & Dynamic Capability Refresh

## 1. 基本資訊
- **日期**: 2026-08-25
- **階段**: Phase 8 - P8-03.5 Real Conversation Integration / Planner Routing Fix
- **目標**: 解決 Production Planner A2A 誤路由問題，建立動態外部 Peer 探索感知機制、PC 配單語意意圖辨識及安全 Fallback 防護網。

---

## 2. 問題背景與 Root-Cause 分析

### 問題現象
當 PCforge 獨立 A2A 伺服器在 `http://127.0.0.1:8001` 運行且 `GET /.well-known/agent-card.json` 包含 `pc_recommendation` 技能時：
- 使用者輸入「我想組一台四萬塊的電腦」，Web UI Trace 卻顯示：
  - `Plan Created (1 task)` ➔ `LOCAL` ➔ `general_qa` ➔ local llama.cpp 約 91 秒 timeout。
- 正確預期應為：
  - `Plan Created (1 task)` ➔ `A2A` ➔ `pc_recommendation` ➔ PCforge 代理人配單。

### 根本原因 (Root Causes)
1. **靜態快照與啟動時序問題 (Startup Snapshot & Lifecycle Issue)**：
   - `OrchestrationService.__init__` 在系統啟動時執行一次 `discover_configured_peers()` 並建立 `CapabilitySummary` 快照給 `Planner`。
   - 若 M.Ber Web 伺服器在 PCforge 啟動前即上線，初始探索失敗後，`CapabilitySummary.a2a_skills` 為空。
   - 後續請求呼叫 `invoke_with_details` 時，從未動態重整能力快照，導致 Planner 永遠看不到後來上線的 `pc_recommendation`。
2. **語意意圖覆蓋 (PC Intent Semantic Coverage)**：
   - 舊有比對僅針對特定少數詞組（例如包含「遊戲電腦」），當使用者說「我想組一台四萬塊的電腦」時，若無法辨識「組」+「電腦」的配單意圖，容易退回預設問答。
3. **91 秒 Timeout 原因**：
   - 當誤路由至 `LOCAL general_qa` 時，系統呼叫本機 llama.cpp (`ChatOpenAI`)。
   - `ModelFactory` 預設 `timeout=30.0` 秒且 LangChain 預設 `max_retries=2`，連續 3 次連線等待達約 90~91 秒後由 `LocalExecutor` 回傳 TIMEOUT。此為誤路由引發的連鎖效應。

---

## 3. 架構修正與技術方案

### A. 動態外部 Peer 探索與即時能力更新 (`AgentDiscoveryService` & `OrchestrationService`)
- 在 [app/a2a/discovery.py](file:///e:/code/ive/M.Ber/app/a2a/discovery.py) 新增 `refresh_unregistered_peers(timeout=2.0)`：僅針對設定檔中尚未成功註冊之外部 Peer 進行即時探測，已註冊者 0 額外網路開銷。
- 在 [app/orchestration/service.py](file:///e:/code/ive/M.Ber/app/orchestration/service.py) 的 `invoke_with_details` 中，每次規劃前呼叫 `_build_capability_summary()` 並傳入 `planner.plan(user_goal, capability_summary=current_caps)`，確保 Planner 始終具備最新能力視野。

### B. 語意感知規劃與非配單防禦 (`Planner` & Prompt System)
- 在 [app/orchestration/planner.py](file:///e:/code/ive/M.Ber/app/orchestration/planner.py) 實作 `_has_pc_recommendation_intent()` 與 `_is_non_recommendation_pc_query()`：
  - **PC 配單意圖**（組裝、開單、預算配置、工作站/主機挑選，如「我想組一台四萬塊的電腦」、「我想配電腦」、「幫我組一台四萬元遊戲主機」）➔ 匹配 A2A `pc_recommendation`。
  - **非配單語句**（過往購買「我昨天買了一台電腦」、故障回報「我的電腦壞了」、概念問答「電腦是怎麼運作的」、軟體問答「Python 可以在電腦上跑嗎」）➔ 嚴格保持 LOCAL `general_qa`。
- 在 `_validate_and_sanitize_tasks` 中加入 A2A 技能白名單驗證：若目標 A2A 技能在可用能力中不存在，自動過濾並安全降級回退為 LOCAL `general_qa`，杜絕幻覺產生不存在之 target。

---

## 4. 變更檔案清單
- [app/a2a/discovery.py](file:///e:/code/ive/M.Ber/app/a2a/discovery.py)：新增 `refresh_unregistered_peers()`。
- [app/orchestration/planner.py](file:///e:/code/ive/M.Ber/app/orchestration/planner.py)：實作語意意圖檢測、更新 Prompt 5 大原則與 Few-shots、更新安全過濾與即時能力參數。
- [app/orchestration/service.py](file:///e:/code/ive/M.Ber/app/orchestration/service.py)：在 `_build_capability_summary` 整合動態探測，在 `invoke_with_details` 即時更新能力。
- [tests/test_planner.py](file:///e:/code/ive/M.Ber/tests/test_planner.py)：新增 6 個 A2A 語意路由與降級回退回歸測試。
- [tests/test_line_gateway.py](file:///e:/code/ive/M.Ber/tests/test_line_gateway.py)：更新時間回應斷言以相容 Persona 模板。

---

## 5. 測試驗證結果
- `tests/test_planner.py`: **49/49 PASSED**
- `tests/test_local_reasoning.py` & `tests/test_pcforge_a2a.py`: **14/14 PASSED**
- `tests/test_line_gateway.py`: **5/5 PASSED**
- Frontend Vitest: **19/19 PASSED**
- 完整測試套件 (`uv run pytest`): **256 PASSED (100% PASS)**

---

## 6. 新手教學 / 觀念解析 (Beginner Explanation)
1. **什麼是「能力感知規劃 (Capability-Aware Planning)」？**
   - 就像餐廳的菜單。如果廚師今天沒有進和牛（PCforge 未上線），點餐員（Planner）就不能接和牛訂單，必須告知或提供家常菜（LOCAL `general_qa`）。
   - 當廚房進了和牛（PCforge 上線被探索到），菜單動態更新，點餐員就能將「我要吃和牛（組電腦）」的訂單精準送給專門廚師。
2. **為什麼不把所有中文句型寫成龐大的 if-else？**
   - 中文表達千變萬化。我們採用「意圖特徵分解（動詞意圖 + 名詞實體）+ 排除語意特徵（過去式、故障、純問答）+ LLM Prompt 規範 + 嚴格白名單過濾」的層次架構，既能自然泛化又具備強健的邊界安全。
