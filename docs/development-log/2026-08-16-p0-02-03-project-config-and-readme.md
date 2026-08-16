# Development Log: P0-02 / P0-03 Project Configuration and README

## 1. Meta Information

- **Date:** 2026-08-16
- **Phase:** Phase 0 — Foundation
- **Task ID:** P0-02 / P0-03 (Foundation Setup)
- **Task Title:** Project Metadata (`pyproject.toml`), `README.md` & Pytest Configuration
- **Status:** COMPLETED

---

## 2. Goal

為 JARVIS 專案建立標準化的 Python 專案元數據設定與說明文件：
1. 建立 `README.md`，清楚說明專案願景、核心原則、專案架構與快速上手指引。
2. 建立 `pyproject.toml`（遵循現代 PEP 517 / PEP 621 標準），集中管理專案依賴與 `pytest` 測試設定。
3. 確保 `pytest` 能夠自動讀取 `pyproject.toml` 的設定並順暢執行所有測試。
4. 驗證專案能在 Python 環境下無痛啟動與被載入。

---

## 3. Why the Change Was Necessary

1. **現代 Python 專案標準**：過去 Python 常散落使用 `setup.py`、`requirements.txt`、`setup.cfg` 等多個檔案，容易造成設定分散。現代 Python 最佳實踐是採用 `pyproject.toml` 作為單一真理來源（Single Source of Truth）。
2. **自動化測試設定一致性**：透過 `pyproject.toml` 中的 `[tool.pytest.ini_options]`，可自動指定測試路徑 `testpaths = ["tests"]` 與輸出選項 `addopts = "-v"`，讓開發者或 CI/CD 只要輸入 `python -m pytest` 即可自動依照統一步驟執行。
3. **專案透明度與指引**：`README.md` 是任何開發者進入專案的第一道大門，清晰記錄 Phase 0 開發路線與執行方式，符合 `AGENTS.md`「理解優先」的原則。

---

## 4. Files Changed

| File | Status | Description |
| :--- | :--- | :--- |
| `README.md` | Created | 專案說明文件、架構圖、快速測試與路線圖說明 |
| `pyproject.toml` | Created | PEP 621 專案元數據、依賴宣告與 pytest 設定 |
| `tests/test_smoke.py` | Modified | 新增 `README.md` 與 `pyproject.toml` 的檢查測試 |
| `docs/development-log/2026-08-16-p0-02-03-project-config-and-readme.md` | Created | 本次任務之完整開發日誌 |

---

## 5. Detailed Explanation

### 5.1 `pyproject.toml`
採用標準 TOML 格式：
```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "jarvis-agent"
version = "0.1.0"
description = "JARVIS - Personal AI Agent Platform"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "pydantic>=2.0.0",
    "python-dotenv>=1.0.0",
    "langchain-core>=0.3.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
addopts = "-v"
```

### 5.2 `README.md`
包含：
- 專案願景與定位（Personal AI Agent Platform）
- 四大核心開發哲學（理解優先、協定優先、漸進開發、安全第一）
- 專案目錄結構樹狀圖
- 快速開始與測試指令說明
- 10 個 Phase 的完整開發路線圖

### 5.3 `tests/test_smoke.py`
擴充了兩項 Smoke Test：
- `test_readme_exists()`: 驗證 `README.md` 存在且非空。
- `test_pyproject_toml_exists()`: 驗證 `pyproject.toml` 存在且包含 `[project]` 與 `[tool.pytest.ini_options]` 區塊。

---

## 6. Before / After Architecture

### Before:
```text
c:\e.v
├── .gitignore
├── AGENTS.md
├── docs/
│   ├── PROJECT_SPEC.md
│   ├── architecture/protocol-versions.md
│   └── development-log/2026-08-16-p0-01-foundation-smoke-test.md
├── app/
│   └── __init__.py
└── tests/
    ├── __init__.py
    └── test_smoke.py
```

### After:
```text
c:\e.v
├── .gitignore
├── AGENTS.md
├── README.md               <-- [NEW] 專案說明與操作指南
├── pyproject.toml          <-- [NEW] 專案設定檔與 pytest 集中管理
├── docs/
│   ├── PROJECT_SPEC.md
│   ├── architecture/protocol-versions.md
│   └── development-log/
│       ├── 2026-08-16-p0-01-foundation-smoke-test.md
│       └── 2026-08-16-p0-02-03-project-config-and-readme.md <-- [NEW]
├── app/
│   └── __init__.py
└── tests/
    ├── __init__.py
    └── test_smoke.py       <-- [UPDATED] 7/7 Smoke Test 驗證
```

---

## 7. Important Code Concepts (新手重要概念)

1. **什麼是 `pyproject.toml`？**
   - **比喻**：它是 Python 專案的「身分證與規格說明書」。
   - **作用**：告訴所有工具（如 pip、pytest、打包工具）這個專案叫什麼名字、版本是多少、需要哪些套件（dependencies），以及測試工具應該去哪裡找測試檔案。
2. **什麼是 `TOML` 格式？**
   - TOML 全名是 *Tom's Obvious, Minimal Language*。
   - 它的特點是極度易讀（比 JSON 直觀、比 YAML 不容易因為縮排失誤而出錯），因此被 Python 官方選為統一的專案設定格式。
3. **為什麼 pytest 會自動抓取 `pyproject.toml`？**
   - pytest 啟動時會從專案根目錄自動搜尋 `pyproject.toml` 中的 `[tool.pytest.ini_options]`，這樣我們就不用每次下指令都手動輸入長長的參數。

---

## 8. Test Results

執行命令：
```powershell
python -m pytest
```

輸出結果：
```text
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0 -- python.exe
cachedir: .pytest_cache
rootdir: C:\e.v
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.13.0, langsmith-0.10.10
collecting ... collected 7 items

tests/test_smoke.py::test_python_version PASSED                          [ 14%]
tests/test_smoke.py::test_core_dependencies_import PASSED                [ 28%]
tests/test_smoke.py::test_app_package_import PASSED                      [ 42%]
tests/test_smoke.py::test_project_spec_exists PASSED                     [ 57%]
tests/test_smoke.py::test_agents_rule_exists PASSED                      [ 71%]
tests/test_smoke.py::test_readme_exists PASSED                           [ 85%]
tests/test_smoke.py::test_pyproject_toml_exists PASSED                   [100%]

============================== 7 passed in 0.06s ==============================
```
**結果：7/7 測試全部通過（Passed）。`pyproject.toml` 成功被識別為 configfile。**

---

## 9. Problems Encountered & Solutions

- **狀況**：需要確保專案設定檔不會引入未到期之功能。
- **處理方式**：`pyproject.toml` 僅定義 Phase 0 所需之基礎依賴與測試工具，不引入未到期的複雜套件。

---

## 10. Beginner Explanation (完全新手解析)

> 🧰 **買新樂高組裝盒的比喻**：
> 
> 想像你買了一盒全新的高級積木（JARVIS 專案）：
> 1. **`README.md` 是「外盒彩盒與說明書前言」**：
>    任何人拿到這盒積木，看一眼封面（`README.md`）就能知道這是什麼模型、有幾塊零件、要怎麼開始拼裝。
> 2. **`pyproject.toml` 是「積木零件清單與組裝工具規範」**：
>    它清楚列出這盒積木需要搭配 3.10 號板手（Python >= 3.10）、必備標準螺絲（Pydantic、Dotenv），並且設定好檢查尺規（pytest）。
> 
> 有了這兩份標準文件，不管是你本人、其他工程師、或是未來的 AI 助手，都能在同一套標準下清楚、安全地協同開發！

---

## 11. Next Step

- **下一個任務**：**環境變數與核心設定管理實作（Settings Management - `config/settings.py` & `.env.example`）**
  - 目標：在 `config/` 資料夾中實作型別安全之 Settings 類別，並搭配 `.env.example` 規範敏感金鑰管理。
