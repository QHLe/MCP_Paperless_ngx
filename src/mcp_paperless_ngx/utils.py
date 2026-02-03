"""Utility helpers for request formatting and normalization."""

from __future__ import annotations

import json
from typing import Any

from .config import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE


def _normalize_page_size(page_size: int) -> int:
    if page_size < 1:
        return DEFAULT_PAGE_SIZE
    return min(page_size, MAX_PAGE_SIZE)


def _normalize_fields(fields: list[str] | None) -> list[str] | None:
    if not fields:
        return None
    cleaned = [field.strip() for field in fields if field and field.strip()]
    return cleaned or None


def _normalize_metadata(metadata: dict[str, Any] | None) -> list[tuple[str, str]]:
    if not metadata:
        return []
    pairs: list[tuple[str, str]] = []
    for key, value in metadata.items():
        key_str = str(key).strip()
        if not key_str or value is None:
            continue
        if isinstance(value, bool):
            pairs.append((key_str, "true" if value else "false"))
        elif isinstance(value, (list, tuple, set)):
            if any(isinstance(item, (dict, list, tuple, set)) for item in value):
                pairs.append((key_str, json.dumps(list(value))))
            else:
                for item in value:
                    if item is None:
                        continue
                    pairs.append((key_str, str(item)))
        elif isinstance(value, dict):
            pairs.append((key_str, json.dumps(value)))
        else:
            pairs.append((key_str, str(value)))
    return pairs


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


__all__ = [
    "_normalize_page_size",
    "_normalize_fields",
    "_normalize_metadata",
    "_build_search_params",
    "_compact_document",
]
