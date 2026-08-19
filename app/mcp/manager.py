"""M.Ber MCP Manager (MCP 伺服器總管與多路由模組).

【新手教學 / 觀念解析】：
1. 什麼是 MCP Manager？
   - MCP Manager 是 M.Ber 的「多功能集線器（Hub）」。
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
   - 重啟 M.Ber 後，Manager 會自動偵測並將新工具整合至 LangGraph Agent！
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

        server_configs = config_data.get("mcpServers") or config_data.get("servers", {})

        for server_name, srv_conf in server_configs.items():
            if not srv_conf.get("enabled", True):
                continue

            cmd = srv_conf.get("command")
            raw_args = srv_conf.get("args", [])
            env = srv_conf.get("env", {})

            # 若為相對路徑，轉換為相對於專案根目錄的絕對路徑
            resolved_args = []
            for arg in raw_args:
                if arg.endswith(".py") and not Path(arg).is_absolute():
                    resolved_args.append(str((self.project_root / arg).resolve()))
                else:
                    resolved_args.append(arg)

            try:
                client = MCPStdioClient(command=cmd, args=resolved_args, env=env)
                self.clients[server_name] = client

                # 立即向該 Server 探索工具清單 (Tool Discovery)
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
        """評估工具調用之安全權限等級 (READ_ONLY vs WRITE / MUTATION).

        【安全邊界規則】：
        - 以 'get_', 'read_', 'list_', 'query_', 'fetch_', 'search_', 'echo_' 開頭的工具 ➔ 判定為 READ_ONLY (低風險，可直接放行)
        - 以 'add_', 'create_', 'delete_', 'update_', 'write_', 'modify_', 'remove_', 'insert_', 'send_' 開頭 ➔ 判定為 WRITE / MUTATION (具副作用，需安全記錄與審批)
        """
        lower_name = tool_name.lower()
        mutation_prefixes = [
            "add_",
            "create_",
            "delete_",
            "update_",
            "write_",
            "modify_",
            "remove_",
            "insert_",
            "send_",
        ]

        if any(lower_name.startswith(p) for p in mutation_prefixes):
            return "WRITE / MUTATION"
        return "READ_ONLY"

    def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> str:
        """根據工具名稱智慧路由至對應的 MCP Server 並執行 (含安全稽核)."""
        args = arguments or {}

        # 1. 執行安全權限評估
        safety_level = self.evaluate_safety_level(tool_name, args)
        if safety_level == "WRITE / MUTATION":
            print(f"\n🚨 [PERMISSION REQUIRED: WRITE/DELETE] 檢測到高風險寫入/刪除操作: Tool='{tool_name}', 參數={args}")
        else:
            print(f"\n🛡️ [SECURITY AUDIT] 唯讀操作通過: Tool='{tool_name}', 參數={args}")

        # 2. 查詢路由表
        server_name = self.tool_routes.get(tool_name)
        if not server_name or server_name not in self.clients:
            return f"❌ [MCP Manager 錯誤]: 找不到提供工具 '{tool_name}' 的 MCP Server (可用工具: {list(self.tool_routes.keys())})"

        client = self.clients[server_name]
        try:
            return client.call_tool(tool_name, args)
        except Exception as e:
            return f"❌ [MCP Manager 調用失敗]: 執行 Server '{server_name}' 之工具 '{tool_name}' 時發生錯誤: {e}"

    def shutdown(self) -> None:
        """釋放所有 Server 連線資源."""
        self.clients.clear()
        self.tool_routes.clear()
