# Support OpenAI-compatible Custom Base URL for Local llama.cpp (支援本機 llama.cpp 自訂 Base URL)

## Date
2026-08-24

## Phase
Phase 8 — Model Factory Local Inference Integration (P8-03.6)

## Goal
讓 `app/orchestration/model_factory.py` 的 OpenAI provider 支援自訂 Base URL (`OPENAI_BASE_URL`)，使 M.Ber 能夠直接無縫連接本機運行的 llama.cpp、vLLM 等 OpenAI-compatible 推論伺服器，同時保持雲端官方 OpenAI API 完全向後相容。

---

## Why the Change was Necessary
1. **本機開源模型推論需求**：
   在學習與隱私保護場景下，開發者常在本機使用 `llama.cpp server` 運行開源 LLM（如 Qwen 2.5、Llama 3 等）。
2. **OpenAI-compatible 協議一致性**：
   llama.cpp 等現代推論後端均原生提供與 OpenAI 完全相容的 `/v1/chat/completions` API 接口。因此，無需在系統中新增專用的 `llama_cpp` provider 類型，只要讓現有的 `openai` provider 能夠指向自訂的 `base_url`，就能最大化重用既有代碼與生態。
3. **金鑰彈性相容**：
   本機 llama.cpp 伺服器預設不檢查金鑰合法性，只要提供非空白且非佔位符的 dummy key（例如 `dummy`、`not-needed`）即可順利通過驗證並調用。

---

## Files Changed
1. **`app/orchestration/model_factory.py`** (MODIFY):
   - 新增讀取環境變數 `OPENAI_BASE_URL`。
   - 在建立 `ChatOpenAI` 時，若 `OPENAI_BASE_URL` 存在且非空白，則傳入 `base_url=openai_base_url`；若未設定，則不傳入 `base_url`，維持官方端點預設行為。
   - 保持 `MODEL_PROVIDER=openai` 與既有金鑰檢驗邏輯相容。
2. **`tests/test_model_factory.py`** (NEW):
   - 新增 7 項完整單元測試，涵蓋：
     - 未提供 `OPENAI_BASE_URL` 時的官方預設行為。
     - 提供 `OPENAI_BASE_URL` 時的自訂 base_url 注入與模型名稱傳遞。
     - `OPENAI_BASE_URL` 為純空白時的安全過濾。
     - 無金鑰、未知 provider、缺少金鑰、多金鑰未指定 provider 時的安全降級行為。

---

## Before / After Architecture

### Before:
```text
.env (MODEL_PROVIDER=openai, OPENAI_API_KEY=sk-...)
   ↓
model_factory.get_chat_model()
   ↓
ChatOpenAI(model=m_name, api_key=openai_key) ──> 固定連接官方 https://api.openai.com/v1
```

### After:
```text
.env (MODEL_PROVIDER=openai, OPENAI_API_KEY=dummy, OPENAI_BASE_URL=http://localhost:8080/v1)
   ↓
model_factory.get_chat_model()
   ↓
ChatOpenAI(model=m_name, api_key=openai_key, base_url=openai_base_url)
   ├─ OPENAI_BASE_URL 未設定 ──> 官方 OpenAI API (https://api.openai.com/v1)
   └─ OPENAI_BASE_URL 已設定 ──> 本機 llama.cpp server (http://localhost:8080/v1)
```

---

## Important Code Concepts

### 1. OpenAI-Compatible Protocol (相容協議)
許多開源 LLM 推論引擎（llama.cpp、vLLM、Ollama、LocalAI）均實作了 OpenAI 的 HTTP API 規格。這意味著客戶端只需修改 `base_url`（伺服器位置），其餘請求格式、流式傳輸與回應結構完全一致。

### 2. Zero Unnecessary Abstraction (最小改動原則)
我們不創建額外的 `LlamaCppProvider`，而是直接沿用 `MODEL_PROVIDER=openai`。這樣 Planner、Router、LocalReasoningAdapter 完全不需要任何改動即可享受到本地模型的支援。

### 3. Optional Environment Variable Fallback
透過 `(os.getenv("OPENAI_BASE_URL") or "").strip() or None`，確保純空白或未定義的環境變數會安全轉為 `None`，不破壞官方 SDK 的預設行為。

---

## Test Results
1. **模型工廠單元測試**：
   ```bash
   uv run pytest tests/test_model_factory.py
   ```
   - 7 項測試全部通過 (`7 passed in 2.08s`)
2. **全系統整合測試**：
   ```bash
   uv run pytest
   ```
   - 全專案 236 項測試全部通過 (100% PASS)

---

## Beginner Explanation
**什麼是 Base URL？為什麼改這個就能連本機 llama.cpp？**

想像你要寄信（傳送 Prompt）：
1. 原本：你固定把信投到「OpenAI 官方郵局」（`api.openai.com`）。
2. 現在：我們給信封加了一個「自訂郵局地址 (Base URL)」的欄位。
   - 如果你不寫，系統依然把信寄到官方郵局。
   - 如果你寫了 `http://localhost:8080/v1`，信件就會直接送到你在自己電腦上開的「llama.cpp 本地小郵局」。
3. 因為本地小郵局和官方郵局使用同一套收發規則（OpenAI 相容協議），所以 M.Ber 的大腦管家（Planner）和推理器完全不需要改變，就能在不花錢、不上傳隱私資料的情況下使用本地模型！

---

## Next Step
- 驗證本地端啟動 llama.cpp server 時，M.Ber Web UI / CLI 透過 `.env` 進行真實離線對話。
