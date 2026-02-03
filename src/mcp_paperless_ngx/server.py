"""MCP server entrypoint for Paperless-ngx."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_TRANSPORT = "stdio"
DEFAULT_LOOKUP_CACHE_TTL_SECONDS = 300.0
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s - %(message)s"

logger = logging.getLogger("mcp_paperless_ngx")

LOOKUP_ENDPOINTS = {
    "tags": "/api/tags/",
    "document_types": "/api/document_types/",
    "correspondents": "/api/correspondents/",
    "storage_paths": "/api/storage_paths/",
    "custom_fields": "/api/custom_fields/",
}

_LOOKUP_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _read_env(name: str, *, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if value is None:
        if required:
            raise ValueError(f"Missing required environment variable: {name}")
        return ""

    value = value.strip()
    if required and not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _read_env_int(name: str, *, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc


def _read_env_float(name: str, *, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number.") from exc


def _resolve_log_level(level_name: str) -> int:
    value = getattr(logging, level_name.strip().upper(), None)
    if isinstance(value, int):
        return value
    return logging.INFO


def _configure_logging() -> None:
    configured_level_name = _read_env("MCP_LOG_LEVEL", default=DEFAULT_LOG_LEVEL)
    resolved_level = _resolve_log_level(configured_level_name)

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(level=resolved_level, format=LOG_FORMAT)
    root_logger.setLevel(resolved_level)
    logger.setLevel(resolved_level)

    configured_level_raw = getattr(logging, configured_level_name.strip().upper(), None)
    if not isinstance(configured_level_raw, int):
        logger.warning(
            "Invalid MCP_LOG_LEVEL=%r. Falling back to INFO.",
            configured_level_name,
        )


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _paperless_verify_setting() -> bool | str:
    verify_ssl = _parse_bool(os.getenv("PAPERLESS_VERIFY_SSL"), default=False)
    ca_bundle = _read_env("PAPERLESS_CA_BUNDLE")
    if verify_ssl and ca_bundle:
        return ca_bundle
    return verify_ssl


def _paperless_timeout_seconds() -> float:
    raw_timeout = _read_env("PAPERLESS_TIMEOUT_SECONDS", default=str(DEFAULT_TIMEOUT_SECONDS))
    try:
        timeout = float(raw_timeout)
    except ValueError as exc:
        raise ValueError("PAPERLESS_TIMEOUT_SECONDS must be a number.") from exc

    if timeout <= 0:
        raise ValueError("PAPERLESS_TIMEOUT_SECONDS must be greater than zero.")
    return timeout


def _paperless_base_url() -> str:
    return _read_env("PAPERLESS_URL", default="http://localhost:8000").rstrip("/")


def _paperless_headers() -> dict[str, str]:
    token = _read_env("PAPERLESS_TOKEN", required=True)
    return {
        "Authorization": f"Token {token}",
        "Accept": "application/json",
    }


def _normalize_page_size(page_size: int) -> int:
    if page_size < 1:
        return DEFAULT_PAGE_SIZE
    return min(page_size, MAX_PAGE_SIZE)


def _lookup_cache_ttl_seconds() -> float:
    ttl = _read_env_float("MCP_LOOKUP_CACHE_TTL_SECONDS", default=DEFAULT_LOOKUP_CACHE_TTL_SECONDS)
    if ttl < 0:
        raise ValueError("MCP_LOOKUP_CACHE_TTL_SECONDS must be zero or greater.")
    return ttl


def _normalize_fields(fields: list[str] | None) -> list[str] | None:
    if not fields:
        return None
    cleaned = [field.strip() for field in fields if field and field.strip()]
    return cleaned or None


def _filter_fields(items: list[dict[str, Any]], fields: list[str] | None) -> list[dict[str, Any]]:
    normalized = _normalize_fields(fields)
    if normalized is None:
        return items
    filtered_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        filtered_items.append({key: item.get(key) for key in normalized})
    return filtered_items


def _get_cached_lookup(name: str) -> list[dict[str, Any]] | None:
    ttl = _lookup_cache_ttl_seconds()
    if ttl == 0:
        return None
    cached = _LOOKUP_CACHE.get(name)
    if not cached:
        return None
    cached_at, data = cached
    if time.time() - cached_at > ttl:
        _LOOKUP_CACHE.pop(name, None)
        return None
    return data


def _set_cached_lookup(name: str, data: list[dict[str, Any]]) -> None:
    ttl = _lookup_cache_ttl_seconds()
    if ttl == 0:
        return
    _LOOKUP_CACHE[name] = (time.time(), data)


def _fetch_paginated(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    endpoint: str,
    label: str,
) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | None]:
    results: list[dict[str, Any]] = []
    page = 1

    while True:
        try:
            response = client.get(
                f"{base_url}{endpoint}",
                headers=headers,
                params={"page": page, "page_size": MAX_PAGE_SIZE},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            return (
                None,
                {
                    "error": "paperless_http_error",
                    "status_code": exc.response.status_code,
                    "message": exc.response.text[:500],
                },
            )
        except httpx.RequestError as exc:
            return None, {"error": "paperless_request_error", "message": str(exc)}

        try:
            payload = response.json()
        except ValueError:
            return None, {
                "error": "unexpected_response",
                "message": f"{label} returned invalid JSON.",
            }

        if not isinstance(payload, dict):
            return None, {
                "error": "unexpected_response",
                "message": f"{label} returned non-object JSON.",
            }

        page_results = payload.get("results")
        if not isinstance(page_results, list):
            return None, {
                "error": "unexpected_response",
                "message": f"{label} response missing results list.",
            }

        for item in page_results:
            if isinstance(item, dict):
                results.append(item)

        if not payload.get("next"):
            break
        page += 1

    return results, None


def _fetch_lookup(
    name: str,
    endpoint: str,
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    *,
    refresh: bool,
) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | None, bool]:
    if not refresh:
        try:
            cached = _get_cached_lookup(name)
        except ValueError as exc:
            return None, {"error": "config_error", "message": str(exc)}, False

        if cached is not None:
            return cached, None, True

    data, error = _fetch_paginated(client, base_url, headers, endpoint, name)
    if error:
        return None, error, False

    try:
        _set_cached_lookup(name, data or [])
    except ValueError as exc:
        return data, {"error": "config_error", "message": str(exc)}, False
    return data, None, False


def _build_search_params(
    query: str,
    page: int,
    page_size: int,
    tag_id: int | None,
    correspondent_id: int | None,
    document_type_id: int | None,
    created_from: str | None,
    created_to: str | None,
    custom_filters: dict[str, Any] | None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "page": max(page, 1),
        "page_size": _normalize_page_size(page_size),
    }

    query = query.strip()
    if query:
        params["query"] = query

    if tag_id is not None:
        params["tags__id"] = tag_id
    if correspondent_id is not None:
        params["correspondent__id"] = correspondent_id
    if document_type_id is not None:
        params["document_type__id"] = document_type_id
    if created_from and created_from.strip():
        params["created__date__gte"] = created_from.strip()
    if created_to and created_to.strip():
        params["created__date__lte"] = created_to.strip()

    if custom_filters:
        for key, value in custom_filters.items():
            key_clean = str(key).strip()
            if not key_clean or value is None:
                continue
            if isinstance(value, str):
                value_clean = value.strip()
                if not value_clean:
                    continue
                params[key_clean] = value_clean
            else:
                params[key_clean] = value

    return params


def _fastmcp_host() -> str:
    return _read_env(
        "MCP_HOST",
        default=_read_env("FASTMCP_HOST", default="127.0.0.1"),
    )


def _fastmcp_port() -> int:
    return _read_env_int(
        "MCP_PORT",
        default=_read_env_int("FASTMCP_PORT", default=8000),
    )


def _fastmcp_log_level() -> str:
    level = _read_env("MCP_LOG_LEVEL", default=DEFAULT_LOG_LEVEL).strip().upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        return DEFAULT_LOG_LEVEL
    return level


def _resolve_transport() -> str:
    transport = _read_env("MCP_TRANSPORT", default=DEFAULT_TRANSPORT).strip().lower()
    if transport in {"stdio", "sse", "streamable-http"}:
        return transport
    logger.warning("Invalid MCP_TRANSPORT=%r. Falling back to stdio.", transport)
    return DEFAULT_TRANSPORT


mcp = FastMCP(
    "Paperless-ngx",
    host=_fastmcp_host(),
    port=_fastmcp_port(),
    log_level=_fastmcp_log_level(),
)


def _compact_document(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": document.get("id"),
        "title": document.get("title"),
        "created": document.get("created"),
        "modified": document.get("modified"),
        "document_type": document.get("document_type"),
        "correspondent": document.get("correspondent"),
        "tags": document.get("tags", []),
        "original_file_name": document.get("original_file_name"),
    }


@mcp.tool()
def healthcheck() -> str:
    """Return service status for basic connectivity checks."""
    return "ok"


@mcp.tool()
def search_documents(
    query: str = "",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    tag_id: int | None = None,
    correspondent_id: int | None = None,
    document_type_id: int | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    custom_filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search Paperless documents by text query and optional filters."""
    _configure_logging()
    params = _build_search_params(
        query=query,
        page=page,
        page_size=page_size,
        tag_id=tag_id,
        correspondent_id=correspondent_id,
        document_type_id=document_type_id,
        created_from=created_from,
        created_to=created_to,
        custom_filters=custom_filters,
    )

    logger.info("search_documents started")
    logger.debug("search_documents params=%s", params)

    try:
        base_url = _paperless_base_url()
        timeout_seconds = _paperless_timeout_seconds()
        verify_setting = _paperless_verify_setting()
        headers = _paperless_headers()
        logger.debug(
            "Paperless request config base_url=%s timeout_seconds=%s verify=%s",
            base_url,
            timeout_seconds,
            verify_setting,
        )

        with httpx.Client(
            timeout=timeout_seconds,
            verify=verify_setting,
        ) as client:
            logger.info("Requesting Paperless documents endpoint")
            response = client.get(
                f"{base_url}/api/documents/",
                headers=headers,
                params=params,
            )
            response.raise_for_status()
    except ValueError as exc:
        logger.error("Configuration error in search_documents: %s", exc)
        return {"error": "config_error", "message": str(exc)}
    except httpx.HTTPStatusError as exc:
        logger.error("Paperless returned HTTP %s", exc.response.status_code)
        return {
            "error": "paperless_http_error",
            "status_code": exc.response.status_code,
            "message": exc.response.text[:500],
        }
    except httpx.RequestError as exc:
        logger.error("Paperless request failed: %s", exc)
        return {"error": "paperless_request_error", "message": str(exc)}

    try:
        payload = response.json()
    except ValueError:
        logger.error("Paperless returned invalid JSON payload.")
        return {"error": "unexpected_response", "message": "Paperless returned invalid JSON."}

    if not isinstance(payload, dict):
        logger.error("Paperless returned JSON payload that is not an object.")
        return {"error": "unexpected_response", "message": "Paperless returned non-object JSON."}

    results = payload.get("results")
    if not isinstance(results, list):
        logger.error("Paperless response missing 'results' list.")
        return {"error": "unexpected_response", "message": "Paperless response missing results list."}

    logger.info(
        "search_documents completed status=%s total=%s returned=%s",
        response.status_code,
        payload.get("count", len(results)),
        len(results),
    )
    return {
        "count": payload.get("count", len(results)),
        "next": payload.get("next"),
        "previous": payload.get("previous"),
        "results": [
            _compact_document(document)
            for document in results
            if isinstance(document, dict)
        ],
    }


@mcp.tool()
def list_lookups(
    refresh: bool = False,
    include: list[str] | None = None,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Return tags, document types, correspondents, storage paths, and custom fields."""
    _configure_logging()
    try:
        base_url = _paperless_base_url()
        timeout_seconds = _paperless_timeout_seconds()
        verify_setting = _paperless_verify_setting()
        headers = _paperless_headers()
    except ValueError as exc:
        logger.error("Configuration error in list_lookups: %s", exc)
        return {"error": "config_error", "message": str(exc)}

    ordered_names = list(LOOKUP_ENDPOINTS.keys())
    if include is None:
        selected_names = ordered_names
    else:
        include_clean = {item.strip() for item in include if item and item.strip()}
        if not include_clean:
            selected_names = ordered_names
        else:
            invalid = sorted(name for name in include_clean if name not in LOOKUP_ENDPOINTS)
            if invalid:
                return {
                    "error": "invalid_request",
                    "message": f"Unknown lookup types: {', '.join(invalid)}",
                    "allowed": ordered_names,
                }
            selected_names = [name for name in ordered_names if name in include_clean]

    data: dict[str, Any] = {}
    counts: dict[str, int] = {}
    errors: dict[str, Any] = {}

    with httpx.Client(timeout=timeout_seconds, verify=verify_setting) as client:
        for name in selected_names:
            endpoint = LOOKUP_ENDPOINTS[name]
            results, error, cache_hit = _fetch_lookup(
                name,
                endpoint,
                client,
                base_url,
                headers,
                refresh=refresh,
            )
            if error:
                errors[name] = error
                logger.error("list_lookups failed for %s: %s", name, error)
                continue
            data[name] = _filter_fields(results or [], fields)
            counts[name] = len(results or [])
            logger.info("list_lookups %s cache_hit=%s count=%s", name, cache_hit, len(results or []))

    data["counts"] = counts
    if errors:
        data["errors"] = errors

    return data


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
