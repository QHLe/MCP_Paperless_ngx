"""MCP server entrypoint for Paperless-ngx."""

from __future__ import annotations

import logging
import time

from .app import mcp
from .config import (
    DEFAULT_LOG_LEVEL,
    DEFAULT_LOOKUP_CACHE_TTL_SECONDS,
    DEFAULT_PAGE_SIZE,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_TRANSPORT,
    LOG_FORMAT,
    MAX_PAGE_SIZE,
    _configure_logging,
    _fastmcp_host,
    _fastmcp_log_level,
    _fastmcp_port,
    _lookup_cache_ttl_seconds,
    _paperless_base_url,
    _paperless_headers,
    _paperless_timeout_seconds,
    _paperless_verify_setting,
    _parse_bool,
    _read_env,
    _read_env_float,
    _read_env_int,
    _resolve_log_level,
    _resolve_transport,
    logger,
)
from .http_client import httpx
from .lookups import (
    LOOKUP_ALIASES,
    LOOKUP_ENDPOINTS,
    MATCHING_ALGORITHM_MAP,
    MATCHING_LOOKUPS,
    _LOOKUP_CACHE,
    _fetch_lookup,
    _fetch_paginated,
    _filter_fields,
    _normalize_lookup_type,
    _normalize_matching_algorithm,
)
from .tools import (
    create_lookup,
    get_document,
    healthcheck,
    list_lookups,
    search_documents,
    update_document,
    upload_document,
)
from .utils import (
    _build_search_params,
    _compact_document,
    _normalize_fields,
    _normalize_metadata,
    _normalize_page_size,
)


def main() -> None:
    """Start the MCP server."""
    _configure_logging()
    transport = _resolve_transport()
    mount_path = _read_env("MCP_MOUNT_PATH", default="/")
    logger.info(
        "Starting Paperless MCP server transport=%s host=%s port=%s",
        transport,
        _fastmcp_host(),
        _fastmcp_port(),
    )
    if transport == "sse":
        mcp.run(transport="sse", mount_path=mount_path)
    elif transport == "streamable-http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()


__all__ = [
    "mcp",
    "main",
    "healthcheck",
    "search_documents",
    "get_document",
    "upload_document",
    "update_document",
    "create_lookup",
    "list_lookups",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "DEFAULT_LOG_LEVEL",
    "DEFAULT_TRANSPORT",
    "DEFAULT_LOOKUP_CACHE_TTL_SECONDS",
    "LOG_FORMAT",
    "LOOKUP_ENDPOINTS",
    "LOOKUP_ALIASES",
    "MATCHING_LOOKUPS",
    "MATCHING_ALGORITHM_MAP",
    "_LOOKUP_CACHE",
    "_read_env",
    "_read_env_int",
    "_read_env_float",
    "_resolve_log_level",
    "_configure_logging",
    "_parse_bool",
    "_paperless_verify_setting",
    "_paperless_timeout_seconds",
    "_paperless_base_url",
    "_paperless_headers",
    "_lookup_cache_ttl_seconds",
    "_fastmcp_host",
    "_fastmcp_port",
    "_fastmcp_log_level",
    "_resolve_transport",
    "_normalize_page_size",
    "_normalize_fields",
    "_normalize_metadata",
    "_build_search_params",
    "_compact_document",
    "_normalize_lookup_type",
    "_normalize_matching_algorithm",
    "_fetch_paginated",
    "_fetch_lookup",
    "_filter_fields",
    "logger",
    "logging",
    "time",
    "httpx",
]
