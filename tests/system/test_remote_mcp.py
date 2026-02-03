import os

import anyio
import httpx
import mcp.types as types
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client


def _extract_text(result: types.CallToolResult) -> str:
    if result.structuredContent is not None:
        return str(result.structuredContent)

    parts: list[str] = []
    for block in result.content:
        block_type = getattr(block, "type", None)
        if block_type == "text" and hasattr(block, "text"):
            parts.append(block.text)
        else:
            parts.append(str(block))
    return "\n".join(parts)


async def _run_healthcheck(url: str, timeout_seconds: float) -> str:
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        async with streamable_http_client(url, http_client=client) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.send_request(
                    types.ClientRequest(
                        types.CallToolRequest(
                            params=types.CallToolRequestParams(
                                name="healthcheck",
                                arguments={},
                            )
                        )
                    ),
                    types.CallToolResult,
                )
                return _extract_text(result)


async def _run_search(url: str, timeout_seconds: float, query: str, page_size: int) -> str:
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        async with streamable_http_client(url, http_client=client) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.send_request(
                    types.ClientRequest(
                        types.CallToolRequest(
                            params=types.CallToolRequestParams(
                                name="search_documents",
                                arguments={
                                    "query": query,
                                    "page": 1,
                                    "page_size": page_size,
                                },
                            )
                        )
                    ),
                    types.CallToolResult,
                )
                return _extract_text(result)


@pytest.mark.system
def test_remote_healthcheck() -> None:
    if os.getenv("MCP_RUN_SYSTEM_TESTS") != "1":
        pytest.skip("Set MCP_RUN_SYSTEM_TESTS=1 to run system tests.")

    url = os.getenv("MCP_REMOTE_URL", "http://localhost:8001/mcp")
    timeout_seconds = float(os.getenv("MCP_REMOTE_TIMEOUT_SECONDS", "10"))
    expected = os.getenv("MCP_REMOTE_EXPECT", "ok").lower()

    result_text = anyio.run(_run_healthcheck, url, timeout_seconds).lower()
    assert expected in result_text


@pytest.mark.system
def test_remote_search_documents() -> None:
    if os.getenv("MCP_RUN_SYSTEM_TESTS") != "1":
        pytest.skip("Set MCP_RUN_SYSTEM_TESTS=1 to run system tests.")

    url = os.getenv("MCP_REMOTE_URL", "http://localhost:8001/mcp")
    timeout_seconds = float(os.getenv("MCP_REMOTE_TIMEOUT_SECONDS", "10"))
    query = os.getenv("MCP_REMOTE_SEARCH_QUERY", "")
    page_size = int(os.getenv("MCP_REMOTE_SEARCH_PAGE_SIZE", "1"))

    result_text = anyio.run(_run_search, url, timeout_seconds, query, page_size)
    assert "count" in result_text or "results" in result_text
