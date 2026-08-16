"""JARVIS MCP Stdio Client (MCP 客戶端連接器).

【新手教學 / 觀念解析】：
1. 什麼是 MCP Client？
   - MCP Client 是主程式（Host）裡的「轉接頭」。
   - 它的任務是啟動 MCP Server（作為子程序 Subprocess），並透過標準輸入/輸出 (stdio) 傳送 JSON-RPC 訊息。

2. 工作流程：
   ① `list_tools()`：向 Server 詢問「你有提供什麼工具？」，取得工具清單與參數規格。
   ② `call_tool(name, args)`：當 Agent 決定使用工具時，將工具名稱與參數發給 Server，等待並解析回傳的結果。
   ③ `close()`：對話結束時安全地關閉子程序，釋放系統資源。
"""

import sys
import os
import anyio
from pathlib import Path
from typing import Any, Dict, List, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import mcp.types as types


class MCPStdioClient:
    """MCP Stdio 客戶端類別.

    管理與指定 MCP Server 腳本的 stdio 連線生命週期，
    支援工具探索與同步/非同步工具呼叫。
    """

    def __init__(
        self,
        server_script_path: Optional[str] = None,
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ):
        """初始化 MCP Client.

        Args:
            server_script_path: MCP Server Python 檔案路徑（可選）
            command: 執行指令（可選，預設為當前 Python 直譯器）
            args: 命令列參數清單（可選）
            env: 環境變數字典（可選）
        """
        project_root = Path(__file__).resolve().parent.parent.parent
        run_cmd = command or sys.executable

        if args is not None:
            run_args = list(args)
        elif server_script_path is not None:
            run_args = [server_script_path]
        else:
            default_script = str(project_root / "mcp_server" / "my_mcp_server.py")
            run_args = [default_script]

        run_env = dict(os.environ)
        if env:
            run_env.update(env)

        # 確保專案根目錄在 PYTHONPATH
        if "PYTHONPATH" not in run_env:
            run_env["PYTHONPATH"] = str(project_root)
        else:
            run_env["PYTHONPATH"] = f"{project_root}{os.pathsep}{run_env['PYTHONPATH']}"

        self.server_script_path = server_script_path
        self._server_params = StdioServerParameters(
            command=run_cmd,
            args=run_args,
            env=run_env,
        )

    async def list_tools_async(self) -> List[Dict[str, Any]]:
        """非同步向 MCP Server 取得工具清單."""
        async with stdio_client(self._server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                return [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": getattr(tool, "input_schema", getattr(tool, "inputSchema", {})),
                    }
                    for tool in tools_result.tools
                ]

    def list_tools(self) -> List[Dict[str, Any]]:
        """同步向 MCP Server 取得工具清單 (提供給同步流程使用)."""
        return anyio.run(self.list_tools_async)

    async def call_tool_async(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> str:
        """非同步呼叫 MCP Server 上的指定工具並回傳字串結果."""
        if arguments is None:
            arguments = {}

        async with stdio_client(self._server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)

                # 解析 TextContent 結果
                output_texts = []
                for content in result.content:
                    if hasattr(content, "text"):
                        output_texts.append(content.text)
                    else:
                        output_texts.append(str(content))

                return "\n".join(output_texts) if output_texts else "[MCP]: 執行成功無回傳內容"

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> str:
        """同步呼叫 MCP Server 上的指定工具 (提供給 LangGraph 節點使用)."""
        return anyio.run(self.call_tool_async, name, arguments)
