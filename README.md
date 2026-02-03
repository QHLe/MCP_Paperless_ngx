# MCP Server for Paperless-ngx

This repository starts with a minimal MCP (Model Context Protocol) server scaffold for Paperless-ngx.

## Current tools

- `healthcheck()` -> returns `ok`
- `search_documents(...)` -> searches documents in Paperless with optional filters
- `get_document(document_id)` -> fetches a single document by ID
- `upload_document(file_path, metadata=None, filename=None)` -> uploads a document to Paperless
- `update_document(document_id, updates)` -> updates metadata for an existing document
- `create_lookup(lookup_type, data, parent_id=None, match=None, matching_algorithm=None, auto_match=True, permissions=None)` -> creates a tag/document type/correspondent/storage path/custom field
- `list_lookups(include=None, fields=None, refresh=false)` -> returns tags, document types, correspondents, storage paths, and custom fields

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
MCP_LOOKUP_CACHE_TTL_SECONDS=300
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
MCP_LOOKUP_CACHE_TTL_SECONDS=300
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

Optional lookup test variables:

```bash
MCP_REMOTE_LOOKUPS_INCLUDE=tags,document_types
MCP_REMOTE_LOOKUPS_FIELDS=id,name
MCP_REMOTE_LOOKUPS_REFRESH=true
```

Optional upload test variables (file path must exist on the server host):

```bash
MCP_REMOTE_UPLOAD_FILE=/path/on/server/invoice.pdf
MCP_REMOTE_UPLOAD_FILENAME=invoice.pdf
MCP_REMOTE_UPLOAD_TITLE=Invoice 2026-01
MCP_REMOTE_UPLOAD_TAGS=1,2
MCP_REMOTE_UPLOAD_DOCUMENT_TYPE=3
MCP_REMOTE_UPLOAD_CORRESPONDENT=7
MCP_REMOTE_UPLOAD_STORAGE_PATH=5
MCP_REMOTE_UPLOAD_CREATED=2026-01-20
MCP_REMOTE_UPLOAD_NOTES=Uploaded via system test
```

Optional create lookup test variables (write operation; opt-in required):

```bash
MCP_REMOTE_CREATE_LOOKUP_ALLOW=1
MCP_REMOTE_CREATE_LOOKUP_TYPE=tag
MCP_REMOTE_CREATE_LOOKUP_NAME=Invoices
# Or pass raw JSON:
# MCP_REMOTE_CREATE_LOOKUP_DATA={"name":"Invoices"}
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
- Upload metadata is sent as multipart form fields; lists become repeated keys, dicts are JSON-encoded.
- `update_document` uses PATCH to send only the fields you want to change.
- Lookup tools are cached in-memory for `MCP_LOOKUP_CACHE_TTL_SECONDS` (set to `0` to disable).
- Pass `refresh=true` to `list_lookups` to bypass cache for that call.
- `list_lookups` accepts `include` to limit which lookups are returned.
- `fields` lets you return only specific keys from each lookup item (omit to get full objects).
- `create_lookup` accepts singular aliases like `tag` or `document_type`.
- `create_lookup` supports `parent_id` for tags, and optional `match`/`matching_algorithm` for auto-matching.
- `auto_match` defaults to true and will set `matching_algorithm=auto` for lookups that support matching.
- Use `permissions` to pass a list of user IDs, or leave it empty/omit to use Paperless defaults.

## Use cases

- **Connectivity check:** verify the MCP server is reachable.
  ```bash
  python mcp_client.py healthcheck
  ```
- **Search documents:** query text or filter by tags, correspondents, document type, dates.
  ```bash
  python mcp_client.py search --query "invoice" --page-size 5
  python mcp_client.py search --query "" --tag-id 12 --created-from 2026-01-01
  ```
- **Get a document by ID:** fetch the full Paperless document JSON.
  ```bash
  python mcp_client.py get-document --document-id 123
  ```
- **List lookups:** fetch tags, document types, correspondents, storage paths, custom fields.
  ```bash
  python mcp_client.py list-lookups --include tags,document_types --fields id,name
  ```
- **Upload documents:** send a file plus metadata.
  ```bash
  python mcp_client.py upload --file-path /path/to/invoice.pdf \
    --metadata '{"title":"Invoice 2026-01","tags":[1,2],"document_type":3}'
  ```
- **Update document metadata:** patch a document without re-uploading.
  ```bash
  python mcp_client.py update-document --document-id 123 \
    --updates '{"title":"Invoice 2026-01 (Reviewed)","tags":[10,12]}'
  ```
- **Create lookup values:** tags, document types, correspondents, storage paths, custom fields.
  ```bash
  python mcp_client.py create-lookup --lookup-type tag --data '{"name":"Invoices"}'
  python mcp_client.py create-lookup --lookup-type tag --data '{"name":"Invoices - 2026"}' \
    --parent-id 12 --match "invoice" --permissions '[]'
  python mcp_client.py create-lookup --lookup-type document_type --data '{"name":"Receipt"}' \
    --matching-algorithm regex --match "receipt"
  ```
- **Custom tool call:** call any tool with raw JSON args.
  ```bash
  python mcp_client.py call --name list_lookups --args '{"include":["tags"]}'
  ```

Tip: for long JSON, you can pass `@path/to/file.json` instead of inline JSON.

## Test client

Use `mcp_client.py` to call tools over Streamable HTTP.

```bash
python mcp_client.py healthcheck
python mcp_client.py search --query invoice --page-size 1
python mcp_client.py get-document --document-id 123
python mcp_client.py list-lookups --include tags,document_types
python mcp_client.py upload --file-path /path/to/invoice.pdf \
  --metadata '{"title":"Invoice 2026-01","tags":[1,2],"document_type":3}'
python mcp_client.py update-document --document-id 123 --updates '{"title":"Updated"}'
python mcp_client.py create-lookup --lookup-type tag --data '{"name":"Invoices"}'
python mcp_client.py create-lookup --lookup-type tag --data '{"name":"Invoices - 2026"}' \
  --parent-id 12 --match "invoice" --permissions '[]'
```

## License

GNU General Public License v3.0 or later (`GPL-3.0-or-later`). See `LICENSE`.
