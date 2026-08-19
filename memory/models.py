"""M.Ber Memory Domain Models (記憶領域模型).

【新手教學 / 觀念解析】：
1. 為什麼 Agent 需要「記憶模型（Memory Model）」？
   - 就像人腦有分「生活習慣」、「工作待辦」、「朋友生日」一樣，Agent 也需要把記住的事情分類儲存。
   - `MemoryItem` 封裝了一筆記憶的完整資訊，包含唯一 ID、記憶文字、記憶類型、建立時間以及額外標籤（Metadata）。

2. 為什麼使用 Pydantic BaseModel？
   - 提供自動型別驗證與 JSON 序列化能力，使資料在傳遞與存取時具備高安全性與清晰型別提示。
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field


class MemoryType(str, Enum):
    """記憶類型枚舉."""

    USER_PREFERENCE = "user_preference"  # 使用者偏好 / 習慣 (例如：「我喜歡喝無糖拿鐵」)
    FACT = "fact"                        # 事實資訊 (例如：「專案名稱是 M.Ber」)
    TASK_CONTEXT = "task_context"        # 任務或對話上下文
    GENERAL = "general"                  # 一般備忘


class MemoryItem(BaseModel):
    """單一記憶項目領域實體 (Domain Entity)."""

    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12], description="記憶唯一識別碼")
    content: str = Field(..., description="記憶文字內容 (Fact / Preference / Note)")
    memory_type: MemoryType = Field(default=MemoryType.GENERAL, description="記憶分類類型")
    created_at: datetime = Field(default_factory=datetime.now, description="記憶建立時間")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="擴充資訊與來源標籤")
