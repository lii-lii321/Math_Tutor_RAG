"""MathMaster Edu MCP Server：把错题本暴露为 Model Context Protocol 工具。

接入方式（以 Claude Desktop 为例，claude_desktop_config.json）：
{
  "mcpServers": {
    "mathmaster": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "env": {"DATABASE_URL": "sqlite:///path/to/data/math_tutor.db"}
    }
  }
}

启动：python -m mcp_server（stdio 传输）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# 保证项目根目录可导入
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.services.agent_tools import build_tools  # noqa: E402
from backend.services.question_service import QuestionService  # noqa: E402

app = Server("mathmaster-edu")


@app.list_tools()
async def list_tools() -> list[Tool]:
    service = QuestionService()
    return [
        Tool(**tool.mcp_schema())
        for tool in build_tools(service, user_id=_resolve_user_id())
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    service = QuestionService()
    for tool in build_tools(service, user_id=_resolve_user_id()):
        if tool.name == name:
            result = tool.handler(**arguments)
            return [TextContent(type="text", text=result)]
    raise ValueError(f"未知工具: {name}")


def _resolve_user_id() -> int:
    """MCP 模式下单用户绑定：环境变量 MM_USER_ID（默认 demo 用户）。"""
    return int(os.getenv("MM_USER_ID", "0")) or _fallback_demo_id()


def _fallback_demo_id() -> int:
    from backend.database import init_db
    from backend.models.orm import User

    init_db(seed_users=True)
    from backend.database import SessionLocal

    with SessionLocal() as session:
        user = session.query(User).filter_by(username=os.getenv("MM_USERNAME", "demo")).first()
        return user.id if user else 1


def main() -> None:
    import anyio

    anyio.run(app.run, stdio_server())


if __name__ == "__main__":
    main()
