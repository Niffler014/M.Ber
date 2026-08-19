"""M.Ber 自有 MCP 伺服器 (Own MCP Server).

【新手教學 / 觀念解析】：
1. 什麼是 MCP Server？
   - MCP Server 是一個完全獨立運行的「工具箱伺服器」。
   - 它透過標準協定對外提供 Tools（工具），讓任何 MCP Client（如 LangGraph Agent）可以發現並調用。

2. 什麼是 stdio 傳輸模式？
   - 伺服器透過 Standard Input / Output (stdin/stdout) 與 Client 子程序進行 JSON-RPC 2.0 雙向通訊。
   - 優點：不需要開啟網路連接埠（Port），極度輕量且安全性高。

3. 【新手擴充教學：如何新增下一個自定義工具？（只需 2 步驟）】：
   - 步驟 1：使用 `@app.tool()` 裝飾器定義一個普通的 Python 函式。
   - 步驟 2：寫好 Type Hints（如 `a: int, b: int -> int`）與 Docstring（函式說明）。
   MCP SDK 會自動幫你把函式名稱、參數型別與說明轉換成標準的 JSON Schema，發佈給 AI 使用！
"""

from datetime import datetime
import anyio
from mcp.server import MCPServer

# 建立 MCP Server 實例，宣告伺服器名稱為 mber-own-mcp-server
app = MCPServer("mber-own-mcp-server")


@app.tool()
def get_current_time() -> str:
    """取得當前系統日期與時間 (Get current system date and time).

    用於回答使用者關於目前時間、日期、幾點幾分等相關問題。
    無須傳入任何參數。
    """
    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"[M.Ber MCP Time Tool]: 目前系統時間為 {current_time_str}"


@app.tool()
def echo_message(message: str) -> str:
    """回傳傳入的文字訊息 (Echo the input message string).

    用於測試 MCP 工具參數傳遞是否正確。

    Args:
        message: 要原樣回傳的文字訊息
    """
    return f"[M.Ber MCP Echo Tool]: 收到回傳請求 -> '{message}'"


def run_server() -> None:
    """啟動 MCP 伺服器 (stdio 模式)."""
    anyio.run(app.run_stdio_async)


if __name__ == "__main__":
    run_server()
