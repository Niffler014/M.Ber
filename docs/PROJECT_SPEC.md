# M.Ber — Personal AI Agent System

**Project Status:** Phase 7 Multi-Agent & Tool Orchestration Layer Completed  
**Specification Version:** 0.7.0  
**Project Type:** Personal AI Agent / Agentic System  
**Primary Language:** Python  
**Primary Orchestration Framework:** LangGraph  
**Agent Framework:** LangChain + LangGraph  
**Tool Protocol:** Model Context Protocol (MCP)  
**Agent-to-Agent Protocol:** Agent2Agent Protocol (A2A)  
**Development Methodology:** Vibe Coding + AI-Assisted Engineering  
**Documentation System:** HackMD + Repository Markdown  
**License:** TBD

---

## 1. Project Vision

M.Ber 是一個以個人使用為核心的 AI Agent 系統。

M.Ber 不只是聊天機器人，而是一個能夠：

1. 理解使用者需求
2. 分析任務
3. 規劃執行步驟
4. 使用 MCP Tools
5. 使用第三方 MCP Servers
6. 與其他 AI Agents 透過 A2A 協作
7. 管理個人資訊與長期記憶
8. 執行電子管家相關任務

的個人 AI 助理。

Project 的長期目標是建立一個具有可擴充性、可觀測性、可測試性與協定互通能力的 Personal Agent Platform。

---

## 2. Core Design Philosophy

M.Ber 遵循以下設計原則。

### 2.1 Agent First

系統不是以「聊天 UI」作為核心，而是以 Agent Orchestration 作為核心。

UI 可以更換，但 Agent Core 不應依賴特定 UI。

---

### 2.2 Protocol First

外部能力應優先透過標準協定整合。

主要協定：

- MCP：Agent 與 Tools / Resources / External Services 的連接
- A2A：Agent 與其他 Agent 的溝通與任務委派

MCP 採用 Host / Client / Server 架構，因此 M.Ber 將扮演 MCP Host，並可管理多個 MCP Client / Server 連線。

A2A 則用於獨立 Agent 之間的互操作與任務協作。A2A 1.0 將 Agent Card、Task、Message、Artifact 等概念標準化。

---

### 2.3 Modular

每個能力都應該盡量模組化。

例如：

```text
Calendar
Media
Files
Research
Memory
System
```

不應把所有功能寫進單一 Agent。

---

### 2.4 Explainable Development

AI 協助開發時，所有程式碼修改都必須留下可理解的紀錄。

每一次 Code Change 都必須回答：

- 為什麼要改？
- 改了什麼？
- 哪些檔案被修改？
- 修改後程式如何運作？
- 對整體架構有什麼影響？
- 如何測試？
- 這次修改學到了什麼？

文件必須以完全沒有相關背景的新手可以理解為標準。

---

### 2.5 Incremental Development

每個 Phase 必須保持 Project 可以執行。

禁止：

```text
一次建立完整 M.Ber
```

改採：

```text
Foundation
→ Agent
→ MCP
→ External MCP
→ Calendar
→ Memory
→ A2A
→ Orchestration
→ UI
```

---

## 3. Long-Term Architecture

預期最終架構：

```text
                         USER
                           │
                           ▼
                    ┌─────────────┐
                    │  M.Ber UI   │
                    └──────┬──────┘
                           │
                           ▼
                ┌────────────────────┐
                │ M.Ber Orchestrator │
                │     LangGraph      │
                └─────────┬──────────┘
                          │
             ┌────────────┼────────────┐
             │            │            │
             ▼            ▼            ▼
          Planning      MCP           A2A
             │            │            │
             │      ┌─────┴─────┐      │
             │      │           │      │
             │    Own MCP   3rd Party │
             │      MCP        MCP     │
             │                          │
             │                    Remote Agents
             │
             ▼
          Execution
             │
             ▼
          Validation
             │
             ▼
           Result

        ┌───────────────────┐
        │ Memory / Storage  │
        └───────────────────┘
```

LangGraph 在本 Project 中負責 Agent Workflow / State / Orchestration。官方文件將 LangGraph 定位為低階 Agent Orchestration Runtime，特別適合 long-running、stateful agent workflow。

---

## 4. Planned Capabilities

### 4.1 Media

預計支援：

- 播放影片
- 暫停影片
- 停止影片
- 查詢目前播放狀態

---

### 4.2 Calendar

預計支援：

- 查詢行程
- 新增行程
- 修改行程
- 刪除行程
- 行程衝突檢查
- 提醒

Calendar Provider 將透過 Adapter / MCP 抽象化，不讓核心 Agent 直接依賴特定 Calendar API。

---

### 4.3 Memory

預計支援：

- Short-term memory
- Long-term memory
- User preferences
- Historical context
- Task-related memory

初期 Storage 優先使用 SQLite，避免過早引入複雜的資料庫架構。

---

### 4.4 MCP

M.Ber 必須具備：

#### Own MCP

由本 Project 自行實作至少一個 MCP Server。

#### Third-party MCP

能夠載入外部 MCP Server。

#### MCP Manager

負責：

- MCP Server configuration
- Connection lifecycle
- Tool discovery
- Tool registration
- Error handling

---

### 4.5 A2A

M.Ber 必須具備：

- A2A Client capability
- A2A Agent capability
- Agent Card
- Agent discovery
- Task delegation
- Task result handling

A2A Agent Card 是 Agent 對外描述自身 identity、capabilities、skills、endpoint 等資訊的標準方式。

---

## 5. Agent Architecture

M.Ber Core 預計包含：

```text
Intent
    ↓
Planner
    ↓
Router
    ↓
Executor
    ↓
Validator
    ↓
Response
```

Router 可以將任務送往：

```text
MCP Tool
```

或：

```text
A2A Agent
```

---

## 6. Safety and Permission Model

任何會產生外部副作用的操作，都必須具備明確的 Permission Boundary。

例如：

```text
讀取資料
```

與：

```text
修改資料
```

必須視為不同等級。

高風險或不可逆操作應預留 Human-in-the-Loop。

例如：

```text
DELETE
SEND
PURCHASE
MODIFY
```

不能只因 LLM 判斷而直接執行。

---

## 7. Development Methodology

本 Project 採用 Vibe Coding，但 Vibe Coding 不代表無規則修改。

標準流程：

```text
User Request
      ↓
AI Understanding
      ↓
Plan
      ↓
Code Change
      ↓
Test
      ↓
Review
      ↓
Development Log
      ↓
Git Commit
```

AI 不得在沒有說明的情況下大規模修改程式碼。

---

## 8. Documentation Requirement

每一次程式碼修改都必須產生 Development Log。

Development Log 必須包含：

1. 修改目標
2. 修改原因
3. 修改檔案
4. Code explanation
5. Architecture impact
6. Before / After
7. Test result
8. Potential problems
9. Beginner explanation
10. Next step

---

## 9. Testing Philosophy

每個功能至少需要：

```text
Unit Test
```

如果功能涉及多個模組：

```text
Integration Test
```

如果涉及外部服務：

```text
Mock Test
```

外部服務不可成為所有測試的必要條件。

---

## 10. Versioning

Project 採 Semantic Versioning：

```text
MAJOR.MINOR.PATCH
```

Phase milestones 使用：

```text
v0.1.0
v0.2.0
v0.3.0
...
v1.0.0
```

---

## 11. Phase Roadmap

### Phase 0
Foundation

### Phase 1
Basic LangGraph Agent

### Phase 2
Own MCP Server

### Phase 3
Third-party MCP Integration

### Phase 4
Calendar Integration

### Phase 5
Memory

### Phase 6
A2A

### Phase 7
Multi-Agent Orchestration

### Phase 8
M.Ber User Interface

### Phase 9
Observability / Evaluation

### Phase 10
Production Hardening

---

## 12. Non-Goals

M.Ber 初期不追求：

- 完美語音助手
- 自主控制所有電腦功能
- 全自動執行所有操作
- 一開始支援大量 MCP
- 一開始建立複雜 Multi-Agent System
- 一開始使用大型分散式架構

所有複雜能力都必須在需求真正出現後才加入。

---

## 13. Definition of Done

一個 Phase 只有在以下條件全部滿足時才算完成：

- Code 可以執行
- Tests 通過
- Architecture 文件更新
- Development Log 完成
- README 更新
- Git commit 完成
- 使用者能解釋該 Phase 的核心概念

最後一項尤其重要。

本 Project 不只追求「AI 寫出來」。

而是追求：

> 使用者逐漸理解自己正在建立的系統。