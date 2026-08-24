# Development Log: 2026-08-24 - P8-03.5 Planner Routing Fix

## 1. 記錄基本資訊
- **日期**：2026-08-24
- **階段**：Phase 8 (P8-03.5 Planner Routing Fix)
- **目標**：修復生產環境結構化規劃器 (`LangChainStructuredPlanningBackend`) 嚴重誤路由問題（例如輸入「我肚子很餓」被錯誤拆解為 `MCP: get_current_time` ➔ `LOCAL: memory_store`），建立明確的語意路由規則、最小可行計劃約束、禁止未經請求之主動副作用，並建立測試套件。

---

## 2. 為什麼需要這次修改（Problem & Root Cause）

### 問題現象
在接入本地 llama.cpp / Qwen 模型進行端到端人工測試時，輸入日常聊天語句：
```text
我肚子很餓
```
觀察到的 Trace 竟然被 Planner 規劃成 2 個任務：
1. `MCP` ➔ `get_current_time`
2. `LOCAL` ➔ `memory_store`（相依於 Task 1）

導致最終回覆變成：「目前系統時間為 ... 已成功記住這項資訊」，完全喪失了正常的對話與推理功能。

### 根本原因分析
1. **Prompt 缺乏「最小可行計劃」原則**：舊有的 System Prompt 包含過多引導 LLM 主動儲存資訊的範例，缺乏「絕大多數請求僅需單一任務」的強約束。
2. **能力清單描述過於簡略**：`CapabilitySummary` 僅向 LLM 提供了 `local_capabilities=['general_qa', 'memory_store']` 等字串清單，沒有說明各能力的核心語意與禁止主動觸發的約束。
3. **缺少泛用防禦過濾器（Generic Guardrail）**：Planner 生成結構化計劃後，直接信任 LLM 的輸出，沒有在後處理階段檢查「使用者是否有明確的記憶／時間查詢意圖」，導致模型發散產生的多餘步驟被直接排入執行佇列。

---

## 3. 架構前後對比（Before vs After）

### 修改前流程（Before）
```text
使用者輸入：「我肚子很餓」
   │
   ▼
Planner (缺少強約束 Prompt 與能力說明)
   │
   ▼
LLM 產生發散計劃:
  - Task 1: MCP → get_current_time
  - Task 2: LOCAL → memory_store (depends_on Task 1)
   │
   ▼
Orchestrator 執行查時間 + 寫入記憶庫
   │
   ▼
最終錯誤回覆：「目前系統時間為 ... 已成功記住這項資訊」
```

### 修改後流程（After）
```text
使用者輸入：「我肚子很餓」
   │
   ▼
Planner (注入 Smallest Valid Plan + 語意描述 + 安全後處理過濾器)
   │
   ▼
LLM 規劃出語意相符的單一任務:
  - Task 1: LOCAL → general_qa
   │
   ▼
Orchestrator 派送至 LocalReasoningAdapter
   │
   ▼
本地 LLM (Qwen / llama.cpp) 生成貼心自然語言建議
   │
   ▼
最終正確回覆：「肚子餓的話，建議可以吃點熱騰騰的食物，例如鍋燒意麵或牛肉麵！」
```

---

## 4. 修改的檔案與主要變更

### 1. `app/orchestration/planner.py`
- **新增能力語意描述字典 (`LOCAL_CAPABILITY_DESCRIPTIONS`)**：
  - `general_qa`：預設本地推理、對話、問答與解釋。
  - `memory_store`：持久化存儲，明確標註「僅在使用者明確要求記錄/儲存時調用，禁止主動添加」。
- **升級 `CapabilitySummary.to_prompt_text()`**：將能力以結構化語意清單注入 Prompt。
- **重構 `LangChainStructuredPlanningBackend.SYSTEM_PROMPT_TEMPLATE`**：
  - 明確定義五大核心規則：Smallest Valid Plan、Default to LOCAL `general_qa`、Necessity-Based MCP Tool Routing、Strict Side-Effect Restriction、A2A Matching。
  - 提供完整且精確的 Few-shot 範例。
- **新增語意安全過濾器 (`_validate_and_sanitize_tasks`)**：
  - 檢測使用者是否具備明確記憶指令（`_has_explicit_memory_intent`）或時間意圖（`_has_explicit_time_intent`）。
  - 若模型輸出未經授權的 `memory_store` 或無關工具調用，自動安全過濾並重整相依關係；若全部無效則平滑降級為單一 `LOCAL general_qa`。
- **完善 `MockDeterministicPlanningBackend`**：同步更新直接記憶請求與 A2A 技能比對的確定性邏輯。

### 2. `tests/conftest.py`
- 新增 pytest 自動使用的環境隔離 fixture（`clean_test_environment`），確保測試套件不受開發者本機 `.env`（例如本地 llama.cpp 離線）的干擾。

### 3. `tests/test_planner.py` & 整合測試
- 新增 14 項專門的路由矩陣測試：
  - `test_planner_hungry_routes_local`
  - `test_planner_greeting_routes_local`
  - `test_planner_dependency_injection_routes_local`
  - `test_planner_current_time_routes_mcp`
  - `test_planner_current_date_routes_mcp`
  - `test_planner_pc_build_routes_a2a`
  - `test_planner_pc_casual_mention_routes_local`
  - `test_planner_explicit_remember_routes_memory`
  - `test_planner_pc_then_remember_routes_a2a_memory`
  - `test_planner_does_not_add_unrequested_memory_side_effect`
  - `test_planner_does_not_use_time_tool_for_hunger`
  - `test_planner_does_not_use_time_tool_for_today_casual_statement`
  - `test_structured_llm_planner_sanitizes_bad_model_output_with_unrequested_side_effects`
  - `test_structured_llm_planner_sanitizes_unrequested_memory_on_a2a_task`

---

## 5. 初學者原理解釋（Beginner Explanation）

### 什麼是「最小可行計劃原則」（Smallest Valid Plan）？
想像你走進一家餐廳跟服務生說：「我好餓喔。」
- **不良的規劃（Over-planning）**：服務生立刻看手錶記錄「現在是晚上 8 點」，然後拿出一本筆記本把「客人說他肚子餓」寫進檔案夾，最後跟你說「我記下來了」。你依然沒有得到食物！
- **正確的規劃（Smallest Valid Plan）**：服務生直接回答：「那我們今天的招牌炒飯很推薦喔，要不要來一份？」——用最少、最直接的步驟滿足使用者的需求。

在 AI 代理人中，如果沒有設定好「最小可行計劃原則」，大語言模型很容易因為看到系統有一堆工具（查時間、寫記憶、調用其他代理人），就熱心地「把所有工具都串一輪」。我們透過清晰的提示詞約束與安全驗證閘門，確保系統只在必要時調用外部工具，其餘日常互動一律使用本地對話模型自然回應。

---

## 6. 測試驗證結果

### 後端測試 (Backend Test Suite)
- 執行指令：`uv run pytest`
- 執行結果：**250 passed in 554s (100% PASS)**
- 涵蓋範圍：
  - `test_planner.py`: 43 passed
  - `test_memory_orchestration.py`: 12 passed
  - `test_local_reasoning.py`: 8 passed
  - `test_web_api.py`: 14 passed
  - `test_execution_trace.py`: 15 passed
  - `test_mcp_activity.py`: 13 passed
  - 其他全體測試：145 passed

### 前端測試與建置 (Frontend Test Suite & Build)
- 執行指令：`npm run test -- --run`
- 執行結果：**19 passed in 32s (100% PASS)**
- 執行指令：`npm run build`
- 執行結果：**TypeScript 編譯與 Vite Bundle 0 error 打包成功**

---

## 7. 下一步（Next Step）
- 進入 Phase 8 後續規劃與端到端本地模型聯調驗證。
