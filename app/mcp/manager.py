"""JARVIS MCP Manager (MCP 伺服器總管與多路由模組).

【新手教學 / 觀念解析】：
1. 什麼是 MCP Manager？
   - MCP Manager 是 JARVIS 的「多功能集線器（Hub）」。
   - 它負責：
     ① 讀取外部設定檔 `config/mcp_servers.json`。
     ② 依據設定，同時啟動並管理多個 MCP Server 子程序。
     ③ 探索所有 Server 提供的工具，並建立「工具 ➔ 伺服器」的自動路由對照表。
     ④ 執行「安全權限審查（Safety Audit）」，區分唯讀操作與寫入操作。

2. 【新手擴充教學：未來如何掛載新的第三方 MCP Server？】：
   - 只需要打開 `config/mcp_servers.json`，在 `mcpServers` 裡面加上你的新伺服器設定，
     例如：
     "my_new_server": {
       "command": "python",
       "args": ["path/to/server.py"],
       "enabled": true
     }
   - 重啟 JARVIS 後，Manager 會自動偵測並將新工具整合至 LangGraph Agent！
"""

import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.mcp.client import MCPStdioClient


class MCPManager:
    """管理多個 MCP Server 連線、工具探索、請求路由與安全稽核之總管類別."""

    def __init__(self, config_path: Optional[str] = None):
        """初始化 MCP Manager.

        Args:
            config_path: mcp_servers.json 設定檔路徑（若無則自動尋找 config/mcp_servers.json）
        """
        self.project_root = Path(__file__).resolve().parent.parent.parent
        if config_path is None:
            config_path = str(self.project_root / "config" / "mcp_servers.json")

        self.config_path = config_path
        self.clients: Dict[str, MCPStdioClient] = {}
        self.tool_routes: Dict[str, str] = {}  # 工具名稱 ➔ 所屬伺服器名稱 (e.g. "read_notes" -> "sqlite_server")
        self.cached_tools: List[Dict[str, Any]] = []

        # 啟動時自動載入設定檔並完成初始化
        self.reload_servers()

    def reload_servers(self) -> None:
        """讀取設定檔並建立所有啟用的 MCP Server 連線池."""
        self.clients.clear()
        self.tool_routes.clear()
        self.cached_tools.clear()

        config_file = Path(self.config_path)
        if not config_file.exists():
            print(f"⚠️ [MCP Manager] 找不到設定檔 {self.config_path}，使用空白連線池。")
            return

        try:
            config_data = json.loads(config_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"❌ [MCP Manager] 解析設定檔失敗: {e}")
            return

        server_configs = config_data.get("mcpServers", {})

        for server_name, srv_conf in server_configs.items():
            if not srv_conf.get("enabled", True):
                continue

            args = srv_conf.get("args", [])
            # 若為相對路徑，轉換為相對於專案根目錄的絕對路徑
            resolved_args = []
            for arg in args:
                if arg.endswith(".py") and not Path(arg).is_absolute():
                    resolved_args.append(str((self.project_root / arg).resolve()))
                else:
                    resolved_args.append(arg)

            server_script = resolved_args[0] if resolved_args else None
            if server_script:
                client = MCPStdioClient(server_script_path=server_script)
                self.clients[server_name] = client

                # 立即向該 Server 探索工具清單 (Tool Discovery)
                try:
                    tools = client.list_tools()
                    for tool in tools:
                        t_name = tool["name"]
                        self.tool_routes[t_name] = server_name
                        self.cached_tools.append(tool)
                except Exception as e:
                    print(f"⚠️ [MCP Manager] 無法連線至伺服器 '{server_name}': {e}")

    def list_all_tools(self) -> List[Dict[str, Any]]:
        """回傳所有已連線 MCP Servers 的所有工具清單 (包含名稱、說明與參數 Schema)."""
        return self.cached_tools

    def evaluate_safety_level(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """安全權限邊界評估 (Safety Model).

        依據操作意圖與命名將操作分類為：
        - `READ_ONLY`: 唯讀操作（查詢、取得、列出），直接放行並記錄。
        - `WRITE / MUTATION`: 修改操作（新增、更新、刪除、寫入），觸發安全稽核攔截日誌。
        """
        mutation_prefixes = ["add_", "create_", "delete_", "update_", "write_", "modify_", "remove_", "insert_", "send_"]
        tool_name_lower = tool_name.lower()

        if any(tool_name_lower.startswith(prefix) for prefix in mutation_prefixes) or "add" in tool_name_lower or "write" in tool_name_lower:
            return "WRITE / MUTATION"

        return "READ_ONLY"

    def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> str:
        """依據工具名稱自動路由至對應的 MCP Server 執行，並執行安全稽核."""
        if arguments is None:
            arguments = {}

        # 1. 執行安全權限檢查與稽核日誌
        safety_level = self.evaluate_safety_level(tool_name, arguments)
        if safety_level == "WRITE / MUTATION":
            print(f"🚨 [SECURITY AUDIT] 檢測到寫入操作: Tool='{tool_name}', 參數={arguments} [權限層級: MUTATION]")
        else:
            print(f"🛡️ [SECURITY AUDIT] 唯讀操作通過: Tool='{tool_name}' [權限層級: READ_ONLY]")

        # 2. 尋找對應的 MCP Server
        server_name = self.tool_routes.get(tool_name)
        if not server_name or server_name not in self.clients:
            return f"[MCP Manager Error]: 未找到提供工具 '{tool_name}' 的 MCP Server (目前已連線伺服器: {list(self.clients.keys())})"

        client = self.clients[server_name]

        # 3. 發送請求至該 Server 子程序
        try:
            return client.call_tool(tool_name, arguments)
        except Exception as e:
            return f"[MCP Manager Error]: 呼叫伺服器 '{server_name}' 之工具 '{tool_name}' 失敗 ({e})"

    def shutdown(self) -> None:
        """釋放所有 Server 連線資源."""
        self.clients.clear()
        self.tool_routes.clear()
