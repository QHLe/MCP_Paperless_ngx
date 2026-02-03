#!/usr/bin/env python3
"""Minimal MCP client for testing the Paperless-ngx MCP server."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import anyio
import httpx
import mcp.types as types
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


def _load_json(value: str | None, *, label: str) -> Any | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.startswith("@"):
        path = raw[1:]
        try:
            with open(path, "r", encoding="utf-8") as handle:
                raw = handle.read()
        except OSError as exc:
            raise ValueError(f"Failed to read {label} from {path}: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON for {label}: {exc}") from exc


def _parse_csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    items = [item.strip() for item in value.split(",") if item and item.strip()]
    return items or None


def _default_url() -> str:
    return os.getenv("MCP_URL") or os.getenv("MCP_REMOTE_URL") or "http://localhost:8001/mcp"


def _default_timeout() -> float:
    return float(os.getenv("MCP_REMOTE_TIMEOUT_SECONDS", "10"))


def _format_result(result: types.CallToolResult) -> str:
    if result.structuredContent is not None:
        return json.dumps(result.structuredContent, indent=2, sort_keys=True)
    text = _extract_text(result)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text
    return json.dumps(parsed, indent=2, sort_keys=True)


async def _call_tool(url: str, timeout: float, name: str, arguments: dict[str, Any]) -> str:
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with streamable_http_client(url, http_client=client) as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.send_request(
                    types.ClientRequest(
                        types.CallToolRequest(
                            params=types.CallToolRequestParams(
                                name=name,
                                arguments=arguments,
                            )
                        )
                    ),
                    types.CallToolResult,
                )
                return _format_result(result)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MCP client for Paperless-ngx")
    parser.add_argument("--url", default=_default_url(), help="MCP streamable HTTP URL")
    parser.add_argument("--timeout", type=float, default=_default_timeout())

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("healthcheck", help="Call healthcheck()")

    search = subparsers.add_parser("search", help="Call search_documents()")
    search.add_argument("--query", default="")
    search.add_argument("--page", type=int, default=1)
    search.add_argument("--page-size", type=int, default=25)
    search.add_argument("--tag-id", type=int)
    search.add_argument("--correspondent-id", type=int)
    search.add_argument("--document-type-id", type=int)
    search.add_argument("--created-from")
    search.add_argument("--created-to")
    search.add_argument("--custom-filters", help="JSON string or @file")

    list_lookups = subparsers.add_parser("list-lookups", help="Call list_lookups()")
    list_lookups.add_argument("--include", help="Comma-separated list")
    list_lookups.add_argument("--fields", help="Comma-separated list")
    list_lookups.add_argument("--refresh", action="store_true")

    upload = subparsers.add_parser("upload", help="Call upload_document()")
    upload.add_argument("--file-path", required=True)
    upload.add_argument("--metadata", help="JSON string or @file")
    upload.add_argument("--filename")

    get_document = subparsers.add_parser("get-document", help="Call get_document()")
    get_document.add_argument("--document-id", type=int, required=True)

    create_lookup = subparsers.add_parser("create-lookup", help="Call create_lookup()")
    create_lookup.add_argument("--lookup-type", required=True)
    create_lookup.add_argument("--data", required=True, help="JSON string or @file")
    create_lookup.add_argument("--parent-id", type=int)
    create_lookup.add_argument("--match")
    create_lookup.add_argument("--matching-algorithm")
    create_lookup.add_argument(
        "--auto-match",
        dest="auto_match",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    create_lookup.add_argument("--permissions", help="JSON list or @file")

    update_document = subparsers.add_parser("update-document", help="Call update_document()")
    update_document.add_argument("--document-id", type=int, required=True)
    update_document.add_argument("--updates", required=True, help="JSON string or @file")

    call = subparsers.add_parser("call", help="Call any tool with JSON args")
    call.add_argument("--name", required=True)
    call.add_argument("--args", default="{}", help="JSON string or @file")

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    tool_name = ""
    tool_args: dict[str, Any] = {}

    try:
        if args.command == "healthcheck":
            tool_name = "healthcheck"
            tool_args = {}
        elif args.command == "search":
            tool_name = "search_documents"
            tool_args = {
                "query": args.query,
                "page": args.page,
                "page_size": args.page_size,
            }
            if args.tag_id is not None:
                tool_args["tag_id"] = args.tag_id
            if args.correspondent_id is not None:
                tool_args["correspondent_id"] = args.correspondent_id
            if args.document_type_id is not None:
                tool_args["document_type_id"] = args.document_type_id
            if args.created_from:
                tool_args["created_from"] = args.created_from
            if args.created_to:
                tool_args["created_to"] = args.created_to
            custom_filters = _load_json(args.custom_filters, label="custom_filters")
            if custom_filters is not None:
                tool_args["custom_filters"] = custom_filters
        elif args.command == "list-lookups":
            tool_name = "list_lookups"
            include = _parse_csv(args.include)
            fields = _parse_csv(args.fields)
            if include is not None:
                tool_args["include"] = include
            if fields is not None:
                tool_args["fields"] = fields
            if args.refresh:
                tool_args["refresh"] = True
        elif args.command == "upload":
            tool_name = "upload_document"
            tool_args = {"file_path": args.file_path}
            metadata = _load_json(args.metadata, label="metadata")
            if metadata is not None:
                tool_args["metadata"] = metadata
            if args.filename:
                tool_args["filename"] = args.filename
        elif args.command == "get-document":
            tool_name = "get_document"
            tool_args = {"document_id": args.document_id}
        elif args.command == "create-lookup":
            tool_name = "create_lookup"
            data = _load_json(args.data, label="data")
            if not isinstance(data, dict):
                raise ValueError("data must be a JSON object")
            tool_args = {
                "lookup_type": args.lookup_type,
                "data": data,
            }
            if args.parent_id is not None:
                tool_args["parent_id"] = args.parent_id
            if args.match is not None:
                tool_args["match"] = args.match
            if args.matching_algorithm is not None:
                tool_args["matching_algorithm"] = args.matching_algorithm
            if args.auto_match is not None:
                tool_args["auto_match"] = args.auto_match
            permissions = _load_json(args.permissions, label="permissions")
            if permissions is not None:
                if not isinstance(permissions, list):
                    raise ValueError("permissions must be a JSON list")
                tool_args["permissions"] = permissions
        elif args.command == "update-document":
            tool_name = "update_document"
            updates = _load_json(args.updates, label="updates")
            if not isinstance(updates, dict):
                raise ValueError("updates must be a JSON object")
            tool_args = {"document_id": args.document_id, "updates": updates}
        elif args.command == "call":
            tool_name = args.name
            parsed_args = _load_json(args.args, label="args")
            if parsed_args is None:
                parsed_args = {}
            if not isinstance(parsed_args, dict):
                raise ValueError("args must be a JSON object")
            tool_args = parsed_args
        else:
            parser.error("Unknown command")
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        output = anyio.run(_call_tool, args.url, args.timeout, tool_name, tool_args)
    except Exception as exc:
        print(f"request failed: {exc}", file=sys.stderr)
        return 1

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
