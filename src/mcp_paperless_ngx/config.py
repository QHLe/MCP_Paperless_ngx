"""Configuration helpers and logging setup."""

from __future__ import annotations

import logging
import os

DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_TRANSPORT = "stdio"
DEFAULT_LOOKUP_CACHE_TTL_SECONDS = 300.0
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s - %(message)s"

logger = logging.getLogger("mcp_paperless_ngx")


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


def _lookup_cache_ttl_seconds() -> float:
    ttl = _read_env_float("MCP_LOOKUP_CACHE_TTL_SECONDS", default=DEFAULT_LOOKUP_CACHE_TTL_SECONDS)
    if ttl < 0:
        raise ValueError("MCP_LOOKUP_CACHE_TTL_SECONDS must be zero or greater.")
    return ttl


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


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "DEFAULT_LOG_LEVEL",
    "DEFAULT_TRANSPORT",
    "DEFAULT_LOOKUP_CACHE_TTL_SECONDS",
    "LOG_FORMAT",
    "logger",
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
]
