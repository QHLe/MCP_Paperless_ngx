"""Lookup metadata helpers and cache handling."""

from __future__ import annotations

import time
from typing import Any

from .config import MAX_PAGE_SIZE, _lookup_cache_ttl_seconds
from .http_client import httpx
from .utils import _normalize_fields

LOOKUP_ENDPOINTS = {
    "tags": "/api/tags/",
    "document_types": "/api/document_types/",
    "correspondents": "/api/correspondents/",
    "storage_paths": "/api/storage_paths/",
    "custom_fields": "/api/custom_fields/",
}
LOOKUP_ALIASES = {
    "tag": "tags",
    "document_type": "document_types",
    "correspondent": "correspondents",
    "storage_path": "storage_paths",
    "custom_field": "custom_fields",
}
MATCHING_LOOKUPS = {"tags", "document_types", "correspondents", "storage_paths"}
MATCHING_ALGORITHM_MAP = {
    "none": 0,
    "any": 1,
    "all": 2,
    "exact": 3,
    "literal": 3,
    "regex": 4,
    "regular_expression": 4,
    "regular expression": 4,
    "fuzzy": 5,
    "auto": 6,
}

_LOOKUP_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _normalize_lookup_type(lookup_type: str) -> str | None:
    if not lookup_type:
        return None
    normalized = lookup_type.strip().lower()
    if not normalized:
        return None
    if normalized in LOOKUP_ENDPOINTS:
        return normalized
    return LOOKUP_ALIASES.get(normalized)


def _normalize_matching_algorithm(value: Any) -> Any:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        key = value.strip().lower()
        if key in MATCHING_ALGORITHM_MAP:
            return MATCHING_ALGORITHM_MAP[key]
    return value


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


__all__ = [
    "LOOKUP_ENDPOINTS",
    "LOOKUP_ALIASES",
    "MATCHING_LOOKUPS",
    "MATCHING_ALGORITHM_MAP",
    "_LOOKUP_CACHE",
    "_normalize_lookup_type",
    "_normalize_matching_algorithm",
    "_filter_fields",
    "_get_cached_lookup",
    "_set_cached_lookup",
    "_fetch_paginated",
    "_fetch_lookup",
]
