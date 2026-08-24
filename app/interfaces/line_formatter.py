"""M.Ber LINE Message Formatter (LINE 回應訊息格式化與長度防護模組).
Phase 8 - P8-05A: LINE Bidirectional Chat Integration

【新手教學 / 觀念解析】：
1. 為什麼需要 LINE Message Formatter？
   - LINE Messaging API 的單則 TextMessage 有 5,000 字元長度限制，
     且單次 reply_message 最多只能攜帶 5 則訊息。
   - 若 LLM 或 Orchestrator 產出很長的文字（如配單報表、長篇分析），直接發送可能導致 LINE API 拋出 400 Bad Request。
   - 因此需要安全切分（Chunking），並保持段落完整，絕不在中文字元或換行中途暴力截斷。
"""

import logging
from typing import List

logger = logging.getLogger("mber.line.formatter")

# LINE 單則訊息建議上限 (保守設定 2000 字元，遠低於平台極限 5000)
DEFAULT_MAX_CHARS_PER_MESSAGE = 2000
# LINE 單次 reply_message 最大訊息則數
MAX_MESSAGES_PER_REPLY = 5


def split_text_into_chunks(
    text: str,
    max_chunk_size: int = DEFAULT_MAX_CHARS_PER_MESSAGE,
    max_chunks: int = MAX_MESSAGES_PER_REPLY,
) -> List[str]:
    """將長文字依據自然段落與標點切分為多則安全的訊息片段.

    Args:
        text: 待切分之原始回應文字
        max_chunk_size: 單則訊息最大字元數 (預設 2000)
        max_chunks: 最多切分則數 (預設 5)

    Returns:
        切分後的非空字串清單 (最多 max_chunks 則)
    """
    clean_text = (text or "").strip()
    if not clean_text:
        return ["M.Ber 處理完成。"]

    if len(clean_text) <= max_chunk_size:
        return [clean_text]

    chunks: List[str] = []
    # 依雙換行（段落）優先切分
    paragraphs = clean_text.split("\n\n")
    current_chunk = ""

    for para in paragraphs:
        para_clean = para.strip()
        if not para_clean:
            continue

        # 若單一自然段落超過上限，則依單換行切分
        if len(para_clean) > max_chunk_size:
            lines = para_clean.split("\n")
            for line in lines:
                line_clean = line.strip()
                if not line_clean:
                    continue

                if len(line_clean) > max_chunk_size:
                    # 極長單行：依據句號/標點切分
                    sub_parts = _split_long_line(line_clean, max_chunk_size)
                    for sp in sub_parts:
                        if len(current_chunk) + len(sp) + 1 <= max_chunk_size:
                            current_chunk = f"{current_chunk}\n{sp}" if current_chunk else sp
                        else:
                            if current_chunk:
                                chunks.append(current_chunk)
                            current_chunk = sp
                else:
                    if len(current_chunk) + len(line_clean) + 1 <= max_chunk_size:
                        current_chunk = f"{current_chunk}\n{line_clean}" if current_chunk else line_clean
                    else:
                        if current_chunk:
                            chunks.append(current_chunk)
                        current_chunk = line_clean
        else:
            if len(current_chunk) + len(para_clean) + 2 <= max_chunk_size:
                current_chunk = f"{current_chunk}\n\n{para_clean}" if current_chunk else para_clean
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = para_clean

    if current_chunk:
        chunks.append(current_chunk)

    # 限制最大則數
    if len(chunks) > max_chunks:
        truncated_chunks = chunks[:max_chunks]
        truncated_chunks[-1] = truncated_chunks[-1] + "\n\n(……篇幅較長，後續內容已省略)"
        return truncated_chunks

    return chunks


def _split_long_line(line: str, max_size: int) -> List[str]:
    """依據標點符號切分超長單行."""
    parts = []
    current = ""
    for char in line:
        current += char
        if len(current) >= max_size or (len(current) >= max_size * 0.8 and char in ("。", "！", "？", "!", "?", "；", ";")):
            parts.append(current)
            current = ""
    if current:
        parts.append(current)
    return parts


def mask_user_id(user_id: str) -> str:
    """遮罩敏感的 LINE User ID (例如 'U_USER_ALICE_123' ➔ 'U_US...123')."""
    if not user_id:
        return "anonymous"
    clean_id = user_id.strip()
    if len(clean_id) <= 8:
        return clean_id
    return f"{clean_id[:4]}...{clean_id[-4:]}"
