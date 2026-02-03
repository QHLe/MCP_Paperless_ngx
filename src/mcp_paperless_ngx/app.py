"""MCP application instance."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .config import _fastmcp_host, _fastmcp_log_level, _fastmcp_port

mcp = FastMCP(
    "Paperless-ngx",
    host=_fastmcp_host(),
    port=_fastmcp_port(),
    log_level=_fastmcp_log_level(),
)

__all__ = ["mcp"]
