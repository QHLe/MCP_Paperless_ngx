# MCP Server for Paperless-ngx

This repository starts with a minimal MCP (Model Context Protocol) server scaffold for Paperless-ngx.

## Current tools

- `healthcheck()` -> returns `ok`
- `search_documents(...)` -> searches documents in Paperless with optional filters

## Requirements

- Python 3.11+

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

## Configuration

For a local non-SSL Paperless server:

```bash
PAPERLESS_URL=http://localhost:8000
PAPERLESS_TOKEN=replace_with_api_token
PAPERLESS_VERIFY_SSL=false
PAPERLESS_TIMEOUT_SECONDS=30
MCP_LOG_LEVEL=INFO
MCP_TRANSPORT=streamable-http
MCP_HOST=127.0.0.1
MCP_PORT=8001
MCP_MOUNT_PATH=/
```

For an HTTPS Paperless server:

```bash
PAPERLESS_URL=https://paperless.example.com
PAPERLESS_TOKEN=replace_with_api_token
PAPERLESS_VERIFY_SSL=true
PAPERLESS_CA_BUNDLE=/path/to/custom-ca.pem  # optional
PAPERLESS_TIMEOUT_SECONDS=30
MCP_LOG_LEVEL=INFO
MCP_TRANSPORT=streamable-http
MCP_HOST=127.0.0.1
MCP_PORT=8001
MCP_MOUNT_PATH=/
```

## Run

```bash
mcp-paperless-ngx
```

## System test (remote MCP)

This calls the running MCP server over Streamable HTTP.

```bash
MCP_RUN_SYSTEM_TESTS=1 \
MCP_REMOTE_URL=http://localhost:8001/mcp \
MCP_REMOTE_TIMEOUT_SECONDS=10 \
pytest -m system
```

Optional search test variables:

```bash
MCP_REMOTE_SEARCH_QUERY=invoice
MCP_REMOTE_SEARCH_PAGE_SIZE=1
```

## Docker (LAN deployment)

Build the image:

```bash
docker build -t mcp-paperless-ngx .
```

Run it on your local network (Streamable HTTP transport):

```bash
docker run --env-file .env \
  -e MCP_TRANSPORT=streamable-http \
  -e MCP_HOST=0.0.0.0 \
  -e MCP_PORT=8001 \
  -p 8001:8001 \
  mcp-paperless-ngx
```

Streamable HTTP endpoint will be available at:

```text
http://<server-ip>:8001/mcp
```

Or with Docker Compose:

```bash
docker compose up --build
```

## Notes

- `page_size` is capped at `100`.
- `MCP_LOG_LEVEL=DEBUG` shows request processing steps in logs.
- Supported search filters: `tag_id`, `correspondent_id`, `document_type_id`, `created_from`, `created_to`.
- Use `custom_filters` to pass raw Paperless filter keys when needed (example: `storage_path__id`).
- The search tool returns compact document summaries (id, title, timestamps, type/correspondent/tags, file name).

## License

GNU General Public License v3.0 or later (`GPL-3.0-or-later`). See `LICENSE`.
