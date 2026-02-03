import json
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


def _parse_csv_list(value: str | None) -> list[str] | None:
    if value is None:
        return None
    items = [item.strip() for item in value.split(",") if item and item.strip()]
    return items or None


def _parse_csv_ints(value: str | None) -> list[int] | None:
    items = _parse_csv_list(value)
    if not items:
        return None
    parsed: list[int] = []
    for item in items:
        try:
            parsed.append(int(item))
        except ValueError:
            continue
    return parsed or None


def _parse_json_env(value: str | None) -> dict[str, object] | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


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


async def _run_list_lookups(
    url: str,
    timeout_seconds: float,
    include: list[str] | None,
    fields: list[str] | None,
    refresh: bool,
) -> str:
    args: dict[str, object] = {}
    if include:
        args["include"] = include
    if fields:
        args["fields"] = fields
    if refresh:
        args["refresh"] = True

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        async with streamable_http_client(url, http_client=client) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.send_request(
                    types.ClientRequest(
                        types.CallToolRequest(
                            params=types.CallToolRequestParams(
                                name="list_lookups",
                                arguments=args,
                            )
                        )
                    ),
                    types.CallToolResult,
                )
                return _extract_text(result)


async def _run_upload_document(
    url: str,
    timeout_seconds: float,
    file_path: str,
    metadata: dict[str, object],
    filename: str | None,
) -> str:
    args: dict[str, object] = {"file_path": file_path, "metadata": metadata}
    if filename:
        args["filename"] = filename

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        async with streamable_http_client(url, http_client=client) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.send_request(
                    types.ClientRequest(
                        types.CallToolRequest(
                            params=types.CallToolRequestParams(
                                name="upload_document",
                                arguments=args,
                            )
                        )
                    ),
                    types.CallToolResult,
                )
                return _extract_text(result)


async def _run_create_lookup(
    url: str,
    timeout_seconds: float,
    lookup_type: str,
    data: dict[str, object],
) -> str:
    args: dict[str, object] = {"lookup_type": lookup_type, "data": data}

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        async with streamable_http_client(url, http_client=client) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.send_request(
                    types.ClientRequest(
                        types.CallToolRequest(
                            params=types.CallToolRequestParams(
                                name="create_lookup",
                                arguments=args,
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


@pytest.mark.system
def test_remote_list_lookups() -> None:
    if os.getenv("MCP_RUN_SYSTEM_TESTS") != "1":
        pytest.skip("Set MCP_RUN_SYSTEM_TESTS=1 to run system tests.")

    url = os.getenv("MCP_REMOTE_URL", "http://localhost:8001/mcp")
    timeout_seconds = float(os.getenv("MCP_REMOTE_TIMEOUT_SECONDS", "10"))
    include = _parse_csv_list(os.getenv("MCP_REMOTE_LOOKUPS_INCLUDE", "tags"))
    fields = _parse_csv_list(os.getenv("MCP_REMOTE_LOOKUPS_FIELDS", ""))
    refresh = os.getenv("MCP_REMOTE_LOOKUPS_REFRESH", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    result_text = anyio.run(
        _run_list_lookups,
        url,
        timeout_seconds,
        include,
        fields,
        refresh,
    ).lower()

    if include:
        for name in include:
            assert name.lower() in result_text
    else:
        assert "tags" in result_text or "document_types" in result_text


@pytest.mark.system
def test_remote_upload_document() -> None:
    if os.getenv("MCP_RUN_SYSTEM_TESTS") != "1":
        pytest.skip("Set MCP_RUN_SYSTEM_TESTS=1 to run system tests.")

    file_path = os.getenv("MCP_REMOTE_UPLOAD_FILE")
    if not file_path:
        pytest.skip("Set MCP_REMOTE_UPLOAD_FILE to a file path on the server host.")

    url = os.getenv("MCP_REMOTE_URL", "http://localhost:8001/mcp")
    timeout_seconds = float(os.getenv("MCP_REMOTE_TIMEOUT_SECONDS", "30"))

    metadata: dict[str, object] = {}
    title = os.getenv("MCP_REMOTE_UPLOAD_TITLE")
    if title:
        metadata["title"] = title

    tags = _parse_csv_ints(os.getenv("MCP_REMOTE_UPLOAD_TAGS"))
    if tags:
        metadata["tags"] = tags

    document_type = os.getenv("MCP_REMOTE_UPLOAD_DOCUMENT_TYPE")
    if document_type:
        metadata["document_type"] = int(document_type)

    correspondent = os.getenv("MCP_REMOTE_UPLOAD_CORRESPONDENT")
    if correspondent:
        metadata["correspondent"] = int(correspondent)

    storage_path = os.getenv("MCP_REMOTE_UPLOAD_STORAGE_PATH")
    if storage_path:
        metadata["storage_path"] = int(storage_path)

    created = os.getenv("MCP_REMOTE_UPLOAD_CREATED")
    if created:
        metadata["created"] = created

    notes = os.getenv("MCP_REMOTE_UPLOAD_NOTES")
    if notes:
        metadata["notes"] = notes

    filename = os.getenv("MCP_REMOTE_UPLOAD_FILENAME")

    result_text = anyio.run(
        _run_upload_document,
        url,
        timeout_seconds,
        file_path,
        metadata,
        filename,
    ).lower()

    assert "error" not in result_text
    assert "task" in result_text or "id" in result_text


@pytest.mark.system
def test_remote_create_lookup() -> None:
    if os.getenv("MCP_RUN_SYSTEM_TESTS") != "1":
        pytest.skip("Set MCP_RUN_SYSTEM_TESTS=1 to run system tests.")

    if os.getenv("MCP_REMOTE_CREATE_LOOKUP_ALLOW") != "1":
        pytest.skip("Set MCP_REMOTE_CREATE_LOOKUP_ALLOW=1 to run create lookup test.")

    lookup_type = os.getenv("MCP_REMOTE_CREATE_LOOKUP_TYPE")
    if not lookup_type:
        pytest.skip("Set MCP_REMOTE_CREATE_LOOKUP_TYPE (e.g. tag, document_type).")

    url = os.getenv("MCP_REMOTE_URL", "http://localhost:8001/mcp")
    timeout_seconds = float(os.getenv("MCP_REMOTE_TIMEOUT_SECONDS", "10"))

    data = _parse_json_env(os.getenv("MCP_REMOTE_CREATE_LOOKUP_DATA"))
    if data is None:
        name = os.getenv("MCP_REMOTE_CREATE_LOOKUP_NAME")
        if not name:
            pytest.skip("Set MCP_REMOTE_CREATE_LOOKUP_DATA or MCP_REMOTE_CREATE_LOOKUP_NAME.")
        data = {"name": name}

    result_text = anyio.run(
        _run_create_lookup,
        url,
        timeout_seconds,
        lookup_type,
        data,
    ).lower()

    assert "error" not in result_text
    assert "id" in result_text or "name" in result_text
