"""MCP tool implementations."""

from __future__ import annotations

import os
from typing import Any

from .app import mcp
from .config import (
    DEFAULT_PAGE_SIZE,
    _configure_logging,
    _paperless_base_url,
    _paperless_headers,
    _paperless_timeout_seconds,
    _paperless_verify_setting,
    logger,
)
from .http_client import httpx
from .lookups import (
    LOOKUP_ENDPOINTS,
    MATCHING_LOOKUPS,
    _LOOKUP_CACHE,
    _fetch_lookup,
    _filter_fields,
    _normalize_lookup_type,
    _normalize_matching_algorithm,
)
from .utils import _build_search_params, _compact_document, _normalize_metadata


@mcp.tool()
def healthcheck() -> str:
    """Return service status for basic connectivity checks.

    Use this to verify the MCP server is reachable end-to-end.
    Returns the string "ok" on success.
    """
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
    """Search Paperless documents by text query and optional filters.

    Parameters:
        query: Full-text search string. Leave empty to list recent documents.
        page: 1-based page index.
        page_size: Number of items per page (capped at 100).
        tag_id: Filter by a specific tag ID (Paperless tag primary key).
        correspondent_id: Filter by correspondent ID.
        document_type_id: Filter by document type ID.
        created_from: Lower bound date (YYYY-MM-DD) for created date.
        created_to: Upper bound date (YYYY-MM-DD) for created date.
        custom_filters: Raw Paperless filter keys/values (e.g., {"storage_path__id": 2}).

    Returns:
        A dict with keys: count, next, previous, results (compact document summaries).
    """
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

        with httpx.Client(timeout=timeout_seconds, verify=verify_setting) as client:
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
def get_document(document_id: int) -> dict[str, Any]:
    """Fetch a single Paperless document by ID.

    Parameters:
        document_id: The numeric Paperless document ID.

    Returns:
        The document JSON returned by Paperless, or an error payload.
    """
    _configure_logging()
    try:
        doc_id = int(document_id)
    except (TypeError, ValueError):
        return {"error": "invalid_request", "message": "document_id must be an integer."}
    if doc_id <= 0:
        return {"error": "invalid_request", "message": "document_id must be positive."}

    try:
        base_url = _paperless_base_url()
        timeout_seconds = _paperless_timeout_seconds()
        verify_setting = _paperless_verify_setting()
        headers = _paperless_headers()
    except ValueError as exc:
        logger.error("Configuration error in get_document: %s", exc)
        return {"error": "config_error", "message": str(exc)}

    logger.info("get_document started id=%s", doc_id)

    try:
        with httpx.Client(timeout=timeout_seconds, verify=verify_setting) as client:
            response = client.get(
                f"{base_url}/api/documents/{doc_id}/",
                headers=headers,
            )
            response.raise_for_status()
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
        return {"error": "unexpected_response", "message": "Paperless returned non-object JSON."}

    logger.info("get_document completed status=%s", response.status_code)
    return payload


@mcp.tool()
def upload_document(
    file_path: str,
    metadata: dict[str, Any] | None = None,
    filename: str | None = None,
) -> dict[str, Any]:
    """Upload a document to Paperless.

    Parameters:
        file_path: Path to the file on disk.
        metadata: Optional dict of Paperless fields (e.g., title, tags, correspondent,
            document_type, storage_path, created, archive_serial_number, notes).
            Lists will be sent as repeated form fields; dicts are JSON-encoded.
        filename: Optional filename override for the uploaded file.

    Returns:
        The JSON response from Paperless (often includes a task ID).
    """
    _configure_logging()
    file_path = file_path.strip()
    if not file_path:
        return {"error": "invalid_request", "message": "file_path is required."}
    if not os.path.isfile(file_path):
        return {"error": "file_not_found", "message": f"File not found: {file_path}"}

    try:
        base_url = _paperless_base_url()
        timeout_seconds = _paperless_timeout_seconds()
        verify_setting = _paperless_verify_setting()
        headers = _paperless_headers()
    except ValueError as exc:
        logger.error("Configuration error in upload_document: %s", exc)
        return {"error": "config_error", "message": str(exc)}

    upload_name = filename.strip() if filename and filename.strip() else os.path.basename(file_path)
    form_data = _normalize_metadata(metadata)

    logger.info("upload_document started filename=%s", upload_name)

    try:
        with open(file_path, "rb") as file_obj:
            with httpx.Client(timeout=timeout_seconds, verify=verify_setting) as client:
                response = client.post(
                    f"{base_url}/api/documents/post_document/",
                    headers=headers,
                    data=form_data,
                    files={
                        "document": (
                            upload_name,
                            file_obj,
                            "application/octet-stream",
                        )
                    },
                )
                response.raise_for_status()
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
    except OSError as exc:
        logger.error("Failed to read file: %s", exc)
        return {"error": "file_error", "message": str(exc)}

    try:
        payload = response.json()
    except ValueError:
        logger.error("Paperless returned invalid JSON payload.")
        return {"error": "unexpected_response", "message": "Paperless returned invalid JSON."}

    if not isinstance(payload, dict):
        return {"error": "unexpected_response", "message": "Paperless returned non-object JSON."}

    logger.info("upload_document completed status=%s", response.status_code)
    return payload


@mcp.tool()
def update_document(document_id: int, updates: dict[str, Any]) -> dict[str, Any]:
    """Update a Paperless document by ID.

    Parameters:
        document_id: The numeric Paperless document ID.
        updates: Dict of fields to update (e.g., title, tags, document_type, correspondent,
            storage_path, created, notes). Use None to clear a field when supported.

    Returns:
        The updated document JSON from Paperless, or an error payload.
    """
    _configure_logging()
    try:
        doc_id = int(document_id)
    except (TypeError, ValueError):
        return {"error": "invalid_request", "message": "document_id must be an integer."}
    if doc_id <= 0:
        return {"error": "invalid_request", "message": "document_id must be positive."}

    if not isinstance(updates, dict) or not updates:
        return {"error": "invalid_request", "message": "updates must be a non-empty object."}

    try:
        base_url = _paperless_base_url()
        timeout_seconds = _paperless_timeout_seconds()
        verify_setting = _paperless_verify_setting()
        headers = _paperless_headers()
    except ValueError as exc:
        logger.error("Configuration error in update_document: %s", exc)
        return {"error": "config_error", "message": str(exc)}

    logger.info("update_document started id=%s", doc_id)
    logger.debug("update_document payload=%s", updates)

    try:
        with httpx.Client(timeout=timeout_seconds, verify=verify_setting) as client:
            response = client.patch(
                f"{base_url}/api/documents/{doc_id}/",
                headers=headers,
                json=updates,
            )
            response.raise_for_status()
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
        return {"error": "unexpected_response", "message": "Paperless returned non-object JSON."}

    logger.info("update_document completed status=%s", response.status_code)
    return payload


@mcp.tool()
def create_lookup(
    lookup_type: str,
    data: dict[str, Any],
    parent_id: int | None = None,
    match: str | None = None,
    matching_algorithm: str | int | None = None,
    auto_match: bool = True,
    permissions: list[int] | None = None,
) -> dict[str, Any]:
    """Create a lookup item such as a tag, document type, or correspondent.

    Parameters:
        lookup_type: One of: tags, document_types, correspondents, storage_paths, custom_fields.
            Singular aliases are accepted (e.g., "tag", "document_type").
        data: A dict of fields for the Paperless object (e.g., {"name": "Invoices"}).
        parent_id: Optional parent tag ID (tags only). Overrides data["parent"] if provided.
        match: Optional match string for auto matching. Overrides data["match"] if provided.
        matching_algorithm: Optional match algorithm (int or label: none, any, all, exact,
            regex, fuzzy, auto). Overrides data["matching_algorithm"] if provided.
        auto_match: When true (default) and lookup_type supports matching, set
            matching_algorithm to auto if not provided.
        permissions: Optional list of user IDs. Leave empty or omit to use Paperless defaults.

    Returns:
        The created object as returned by Paperless, or an error payload.
    """
    _configure_logging()
    lookup_key = _normalize_lookup_type(lookup_type)
    if not lookup_key:
        return {
            "error": "invalid_request",
            "message": "lookup_type is required.",
            "allowed": list(LOOKUP_ENDPOINTS.keys()),
        }

    if not isinstance(data, dict) or not data:
        return {"error": "invalid_request", "message": "data must be a non-empty object."}

    payload = dict(data)
    if parent_id is not None:
        if lookup_key != "tags":
            return {
                "error": "invalid_request",
                "message": "parent_id is only supported for tags.",
            }
        try:
            payload["parent"] = int(parent_id)
        except (TypeError, ValueError):
            return {"error": "invalid_request", "message": "parent_id must be an integer."}

    if match is not None:
        payload["match"] = match

    if matching_algorithm is not None:
        payload["matching_algorithm"] = matching_algorithm

    if permissions is not None:
        if not isinstance(permissions, list):
            return {
                "error": "invalid_request",
                "message": "permissions must be a list of user ids.",
            }
        payload["permissions"] = permissions

    if "matching_algorithm" in payload:
        if payload["matching_algorithm"] is None:
            payload.pop("matching_algorithm")
        else:
            payload["matching_algorithm"] = _normalize_matching_algorithm(
                payload["matching_algorithm"]
            )

    if auto_match and lookup_key in MATCHING_LOOKUPS and "matching_algorithm" not in payload:
        payload["matching_algorithm"] = _normalize_matching_algorithm("auto")

    try:
        base_url = _paperless_base_url()
        timeout_seconds = _paperless_timeout_seconds()
        verify_setting = _paperless_verify_setting()
        headers = _paperless_headers()
    except ValueError as exc:
        logger.error("Configuration error in create_lookup: %s", exc)
        return {"error": "config_error", "message": str(exc)}

    endpoint = LOOKUP_ENDPOINTS[lookup_key]
    logger.info("create_lookup started type=%s", lookup_key)

    try:
        with httpx.Client(timeout=timeout_seconds, verify=verify_setting) as client:
            response = client.post(
                f"{base_url}{endpoint}",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
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

    _LOOKUP_CACHE.pop(lookup_key, None)
    logger.info("create_lookup completed status=%s", response.status_code)
    return payload


@mcp.tool()
def list_lookups(
    refresh: bool = False,
    include: list[str] | None = None,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Return tags, document types, correspondents, storage paths, and custom fields.

    Parameters:
        refresh: If true, bypass in-memory cache and fetch from Paperless now.
        include: Optional list limiting which lookups to return. Allowed values:
            ["tags", "document_types", "correspondents", "storage_paths", "custom_fields"].
        fields: Optional list of keys to keep in each returned item. If omitted,
            full objects from Paperless are returned.

    Returns:
        A dict containing selected lookup lists, a "counts" map, and optional "errors".
    """
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


__all__ = [
    "healthcheck",
    "search_documents",
    "get_document",
    "upload_document",
    "update_document",
    "create_lookup",
    "list_lookups",
]
