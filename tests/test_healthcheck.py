import json

import mcp_paperless_ngx.server as server


class _DummyResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.status_code = 200
        self.text = ""

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class _DummyClient:
    def __init__(self, payload: dict[str, object], captured: dict[str, object]) -> None:
        self._payload = payload
        self._captured = captured
        self._calls = 0

    def __enter__(self) -> "_DummyClient":
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def get(self, url: str, *, headers: dict[str, str], params: dict[str, object]) -> _DummyResponse:
        self._captured["url"] = url
        self._captured["headers"] = headers
        self._captured["params"] = params
        self._calls += 1
        if self._calls == 1:
            return _DummyResponse(self._payload)
        return _DummyResponse({"count": 0, "next": None, "previous": None, "results": []})
        return _DummyResponse(self._payload)


def test_healthcheck_returns_ok() -> None:
    assert server.healthcheck() == "ok"


def test_search_documents_calls_paperless(monkeypatch) -> None:
    captured: dict[str, object] = {}
    payload = {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                "id": 17,
                "title": "Invoice 2026-01",
                "created": "2026-01-20T10:30:00Z",
                "modified": "2026-01-20T10:30:00Z",
                "document_type": 2,
                "correspondent": 7,
                "tags": [3, 8],
                "original_file_name": "invoice.pdf",
            }
        ],
    }

    def fake_client(*, timeout: float, verify: bool | str) -> _DummyClient:
        captured["timeout"] = timeout
        captured["verify"] = verify
        return _DummyClient(payload, captured)

    monkeypatch.setattr(server.httpx, "Client", fake_client)
    monkeypatch.setenv("PAPERLESS_URL", "http://localhost:8000")
    monkeypatch.setenv("PAPERLESS_TOKEN", "test-token")
    monkeypatch.setenv("PAPERLESS_VERIFY_SSL", "false")
    monkeypatch.setenv("MCP_LOG_LEVEL", "DEBUG")

    result = server.search_documents(query="invoice", page=2, page_size=10)

    assert result["count"] == 1
    assert captured["url"] == "http://localhost:8000/api/documents/"
    assert captured["params"] == {"query": "invoice", "page": 2, "page_size": 10}
    assert captured["headers"] == {
        "Authorization": "Token test-token",
        "Accept": "application/json",
    }
    assert captured["verify"] is False


def test_search_documents_includes_filters(monkeypatch) -> None:
    captured: dict[str, object] = {}
    payload = {"count": 0, "next": None, "previous": None, "results": []}

    def fake_client(*, timeout: float, verify: bool | str) -> _DummyClient:
        captured["timeout"] = timeout
        captured["verify"] = verify
        return _DummyClient(payload, captured)

    monkeypatch.setattr(server.httpx, "Client", fake_client)
    monkeypatch.setenv("PAPERLESS_URL", "http://localhost:8000")
    monkeypatch.setenv("PAPERLESS_TOKEN", "test-token")
    monkeypatch.setenv("PAPERLESS_VERIFY_SSL", "false")
    monkeypatch.setenv("MCP_LOG_LEVEL", "DEBUG")

    _ = server.search_documents(
        query="invoice",
        page=3,
        page_size=500,
        tag_id=5,
        correspondent_id=6,
        document_type_id=7,
        created_from="2026-01-01",
        created_to="2026-01-31",
        custom_filters={"storage_path__id": 2, "owner__id": 12, "ignored_empty": ""},
    )

    assert captured["params"] == {
        "query": "invoice",
        "page": 3,
        "page_size": 100,
        "tags__id": 5,
        "correspondent__id": 6,
        "document_type__id": 7,
        "created__date__gte": "2026-01-01",
        "created__date__lte": "2026-01-31",
        "storage_path__id": 2,
        "owner__id": 12,
    }


def test_search_documents_supports_ssl_bundle(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_client(*, timeout: float, verify: bool | str) -> _DummyClient:
        captured["verify"] = verify
        return _DummyClient({"count": 0, "results": []}, captured)

    monkeypatch.setattr(server.httpx, "Client", fake_client)
    monkeypatch.setenv("PAPERLESS_URL", "https://paperless.internal")
    monkeypatch.setenv("PAPERLESS_TOKEN", "test-token")
    monkeypatch.setenv("PAPERLESS_VERIFY_SSL", "true")
    monkeypatch.setenv("PAPERLESS_CA_BUNDLE", "/etc/ssl/certs/paperless-ca.pem")
    monkeypatch.setenv("MCP_LOG_LEVEL", "INFO")

    _ = server.search_documents(query="")

    assert captured["verify"] == "/etc/ssl/certs/paperless-ca.pem"


def test_search_documents_requires_token(monkeypatch) -> None:
    monkeypatch.setenv("PAPERLESS_URL", "http://localhost:8000")
    monkeypatch.delenv("PAPERLESS_TOKEN", raising=False)
    monkeypatch.setenv("MCP_LOG_LEVEL", "INFO")

    result = server.search_documents(query="invoice")

    assert result["error"] == "config_error"


def test_resolve_log_level_defaults_to_info() -> None:
    assert server._resolve_log_level("DEBUG") == server.logging.DEBUG
    assert server._resolve_log_level("not-a-level") == server.logging.INFO


def test_list_lookups_returns_combined(monkeypatch) -> None:
    captured: dict[str, object] = {}
    payload = {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [{"id": 1, "name": "Sample"}],
    }

    def fake_client(*, timeout: float, verify: bool | str) -> _DummyClient:
        return _DummyClient(payload, captured)

    monkeypatch.setattr(server.httpx, "Client", fake_client)
    monkeypatch.setenv("PAPERLESS_URL", "http://localhost:8000")
    monkeypatch.setenv("PAPERLESS_TOKEN", "test-token")
    monkeypatch.setenv("PAPERLESS_VERIFY_SSL", "false")
    monkeypatch.setenv("MCP_LOG_LEVEL", "INFO")
    monkeypatch.setenv("MCP_LOOKUP_CACHE_TTL_SECONDS", "0")

    result = server.list_lookups()

    assert "tags" in result
    assert "document_types" in result
    assert "correspondents" in result
    assert "storage_paths" in result
    assert "custom_fields" in result
    assert result["counts"]["tags"] == 1


def test_list_lookups_include_filters(monkeypatch) -> None:
    captured: dict[str, object] = {}
    payload = {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [{"id": 1, "name": "Sample"}],
    }

    def fake_client(*, timeout: float, verify: bool | str) -> _DummyClient:
        return _DummyClient(payload, captured)

    monkeypatch.setattr(server.httpx, "Client", fake_client)
    monkeypatch.setenv("PAPERLESS_URL", "http://localhost:8000")
    monkeypatch.setenv("PAPERLESS_TOKEN", "test-token")
    monkeypatch.setenv("PAPERLESS_VERIFY_SSL", "false")
    monkeypatch.setenv("MCP_LOG_LEVEL", "INFO")
    monkeypatch.setenv("MCP_LOOKUP_CACHE_TTL_SECONDS", "0")

    result = server.list_lookups(include=["tags", "document_types"])

    assert "tags" in result
    assert "document_types" in result
    assert "correspondents" not in result


def test_list_lookups_fields_filter(monkeypatch) -> None:
    captured: dict[str, object] = {}
    payload = {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [{"id": 1, "name": "Sample", "slug": "sample"}],
    }

    def fake_client(*, timeout: float, verify: bool | str) -> _DummyClient:
        return _DummyClient(payload, captured)

    monkeypatch.setattr(server.httpx, "Client", fake_client)
    monkeypatch.setenv("PAPERLESS_URL", "http://localhost:8000")
    monkeypatch.setenv("PAPERLESS_TOKEN", "test-token")
    monkeypatch.setenv("PAPERLESS_VERIFY_SSL", "false")
    monkeypatch.setenv("MCP_LOG_LEVEL", "INFO")
    monkeypatch.setenv("MCP_LOOKUP_CACHE_TTL_SECONDS", "0")

    result = server.list_lookups(fields=["id", "name"])

    assert result["tags"][0] == {"id": 1, "name": "Sample"}


def test_list_lookups_invalid_include(monkeypatch) -> None:
    monkeypatch.setenv("PAPERLESS_URL", "http://localhost:8000")
    monkeypatch.setenv("PAPERLESS_TOKEN", "test-token")
    monkeypatch.setenv("PAPERLESS_VERIFY_SSL", "false")
    monkeypatch.setenv("MCP_LOG_LEVEL", "INFO")

    result = server.list_lookups(include=["not-a-real-type"])

    assert result["error"] == "invalid_request"


def test_list_lookups_refresh_bypasses_cache(monkeypatch) -> None:
    captured: dict[str, object] = {}
    payload = {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [{"id": 1, "name": "Fresh"}],
    }

    def fake_client(*, timeout: float, verify: bool | str) -> _DummyClient:
        return _DummyClient(payload, captured)

    monkeypatch.setattr(server.httpx, "Client", fake_client)
    monkeypatch.setenv("PAPERLESS_URL", "http://localhost:8000")
    monkeypatch.setenv("PAPERLESS_TOKEN", "test-token")
    monkeypatch.setenv("PAPERLESS_VERIFY_SSL", "false")
    monkeypatch.setenv("MCP_LOG_LEVEL", "INFO")
    monkeypatch.setenv("MCP_LOOKUP_CACHE_TTL_SECONDS", "300")

    server._LOOKUP_CACHE["tags"] = (server.time.time(), [{"id": 99, "name": "Cached"}])

    result = server.list_lookups(include=["tags"], refresh=True)

    assert result["tags"][0]["id"] == 1


def test_create_lookup_posts_payload(monkeypatch) -> None:
    captured: dict[str, object] = {}
    payload = {"id": 99, "name": "Invoices"}
    auto_value = server.MATCHING_ALGORITHM_MAP["auto"]

    class _CreateClient:
        def __init__(self, payload: dict[str, object], captured: dict[str, object]) -> None:
            self._payload = payload
            self._captured = captured

        def __enter__(self) -> "_CreateClient":
            return self

        def __exit__(self, *_: object) -> bool:
            return False

        def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> _DummyResponse:
            self._captured["url"] = url
            self._captured["headers"] = headers
            self._captured["json"] = json
            return _DummyResponse(self._payload)

    def fake_client(*, timeout: float, verify: bool | str) -> _CreateClient:
        return _CreateClient(payload, captured)

    monkeypatch.setattr(server.httpx, "Client", fake_client)
    monkeypatch.setenv("PAPERLESS_URL", "http://localhost:8000")
    monkeypatch.setenv("PAPERLESS_TOKEN", "test-token")
    monkeypatch.setenv("PAPERLESS_VERIFY_SSL", "false")
    monkeypatch.setenv("MCP_LOG_LEVEL", "INFO")

    result = server.create_lookup("tags", {"name": "Invoices"})

    assert result["id"] == 99
    assert captured["url"] == "http://localhost:8000/api/tags/"
    assert captured["json"] == {"name": "Invoices", "matching_algorithm": auto_value}


def test_create_lookup_accepts_alias(monkeypatch) -> None:
    payload = {"id": 5, "name": "Receipt"}

    class _CreateClient:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def __enter__(self) -> "_CreateClient":
            return self

        def __exit__(self, *_: object) -> bool:
            return False

        def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> _DummyResponse:
            assert url.endswith("/api/document_types/")
            return _DummyResponse(self._payload)

    def fake_client(*, timeout: float, verify: bool | str) -> _CreateClient:
        return _CreateClient(payload)

    monkeypatch.setattr(server.httpx, "Client", fake_client)
    monkeypatch.setenv("PAPERLESS_URL", "http://localhost:8000")
    monkeypatch.setenv("PAPERLESS_TOKEN", "test-token")
    monkeypatch.setenv("PAPERLESS_VERIFY_SSL", "false")
    monkeypatch.setenv("MCP_LOG_LEVEL", "INFO")

    result = server.create_lookup("document_type", {"name": "Receipt"})

    assert result["id"] == 5


def test_create_lookup_sets_parent_tag(monkeypatch) -> None:
    captured: dict[str, object] = {}
    payload = {"id": 7, "name": "Parented"}

    class _CreateClient:
        def __init__(self, payload: dict[str, object], captured: dict[str, object]) -> None:
            self._payload = payload
            self._captured = captured

        def __enter__(self) -> "_CreateClient":
            return self

        def __exit__(self, *_: object) -> bool:
            return False

        def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> _DummyResponse:
            self._captured["json"] = json
            return _DummyResponse(self._payload)

    def fake_client(*, timeout: float, verify: bool | str) -> _CreateClient:
        return _CreateClient(payload, captured)

    monkeypatch.setattr(server.httpx, "Client", fake_client)
    monkeypatch.setenv("PAPERLESS_URL", "http://localhost:8000")
    monkeypatch.setenv("PAPERLESS_TOKEN", "test-token")
    monkeypatch.setenv("PAPERLESS_VERIFY_SSL", "false")
    monkeypatch.setenv("MCP_LOG_LEVEL", "INFO")

    _ = server.create_lookup("tags", {"name": "Child"}, parent_id=42)

    assert captured["json"]["parent"] == 42


def test_create_lookup_disable_auto_match(monkeypatch) -> None:
    captured: dict[str, object] = {}
    payload = {"id": 8, "name": "Manual"}

    class _CreateClient:
        def __init__(self, payload: dict[str, object], captured: dict[str, object]) -> None:
            self._payload = payload
            self._captured = captured

        def __enter__(self) -> "_CreateClient":
            return self

        def __exit__(self, *_: object) -> bool:
            return False

        def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> _DummyResponse:
            self._captured["json"] = json
            return _DummyResponse(self._payload)

    def fake_client(*, timeout: float, verify: bool | str) -> _CreateClient:
        return _CreateClient(payload, captured)

    monkeypatch.setattr(server.httpx, "Client", fake_client)
    monkeypatch.setenv("PAPERLESS_URL", "http://localhost:8000")
    monkeypatch.setenv("PAPERLESS_TOKEN", "test-token")
    monkeypatch.setenv("PAPERLESS_VERIFY_SSL", "false")
    monkeypatch.setenv("MCP_LOG_LEVEL", "INFO")

    _ = server.create_lookup("tags", {"name": "Manual"}, auto_match=False)

    assert "matching_algorithm" not in captured["json"]


def test_create_lookup_normalizes_matching_algorithm(monkeypatch) -> None:
    captured: dict[str, object] = {}
    payload = {"id": 9, "name": "Regex"}

    class _CreateClient:
        def __init__(self, payload: dict[str, object], captured: dict[str, object]) -> None:
            self._payload = payload
            self._captured = captured

        def __enter__(self) -> "_CreateClient":
            return self

        def __exit__(self, *_: object) -> bool:
            return False

        def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> _DummyResponse:
            self._captured["json"] = json
            return _DummyResponse(self._payload)

    def fake_client(*, timeout: float, verify: bool | str) -> _CreateClient:
        return _CreateClient(payload, captured)

    monkeypatch.setattr(server.httpx, "Client", fake_client)
    monkeypatch.setenv("PAPERLESS_URL", "http://localhost:8000")
    monkeypatch.setenv("PAPERLESS_TOKEN", "test-token")
    monkeypatch.setenv("PAPERLESS_VERIFY_SSL", "false")
    monkeypatch.setenv("MCP_LOG_LEVEL", "INFO")

    _ = server.create_lookup(
        "tags",
        {"name": "Regex"},
        match="INV-.*",
        matching_algorithm="regex",
    )

    assert captured["json"]["matching_algorithm"] == server.MATCHING_ALGORITHM_MAP["regex"]


def test_create_lookup_includes_permissions(monkeypatch) -> None:
    captured: dict[str, object] = {}
    payload = {"id": 10, "name": "Permitted"}

    class _CreateClient:
        def __init__(self, payload: dict[str, object], captured: dict[str, object]) -> None:
            self._payload = payload
            self._captured = captured

        def __enter__(self) -> "_CreateClient":
            return self

        def __exit__(self, *_: object) -> bool:
            return False

        def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> _DummyResponse:
            self._captured["json"] = json
            return _DummyResponse(self._payload)

    def fake_client(*, timeout: float, verify: bool | str) -> _CreateClient:
        return _CreateClient(payload, captured)

    monkeypatch.setattr(server.httpx, "Client", fake_client)
    monkeypatch.setenv("PAPERLESS_URL", "http://localhost:8000")
    monkeypatch.setenv("PAPERLESS_TOKEN", "test-token")
    monkeypatch.setenv("PAPERLESS_VERIFY_SSL", "false")
    monkeypatch.setenv("MCP_LOG_LEVEL", "INFO")

    _ = server.create_lookup("tags", {"name": "Permitted"}, permissions=[])

    assert captured["json"]["permissions"] == []


def test_create_lookup_invalid_type() -> None:
    result = server.create_lookup("", {"name": "Bad"})
    assert result["error"] == "invalid_request"


def test_create_lookup_missing_data() -> None:
    result = server.create_lookup("tags", {})
    assert result["error"] == "invalid_request"


def test_upload_document_sends_file_and_metadata(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}
    payload = {"task_id": "abc123"}

    class _UploadClient:
        def __init__(self, payload: dict[str, object], captured: dict[str, object]) -> None:
            self._payload = payload
            self._captured = captured

        def __enter__(self) -> "_UploadClient":
            return self

        def __exit__(self, *_: object) -> bool:
            return False

        def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            data: list[tuple[str, str]],
            files: dict[str, tuple[str, object, str]],
        ) -> _DummyResponse:
            self._captured["url"] = url
            self._captured["headers"] = headers
            self._captured["data"] = data
            self._captured["files"] = files
            return _DummyResponse(self._payload)

    def fake_client(*, timeout: float, verify: bool | str) -> _UploadClient:
        return _UploadClient(payload, captured)

    monkeypatch.setattr(server.httpx, "Client", fake_client)
    monkeypatch.setenv("PAPERLESS_URL", "http://localhost:8000")
    monkeypatch.setenv("PAPERLESS_TOKEN", "test-token")
    monkeypatch.setenv("PAPERLESS_VERIFY_SSL", "false")
    monkeypatch.setenv("MCP_LOG_LEVEL", "INFO")

    file_path = tmp_path / "invoice.pdf"
    file_path.write_bytes(b"test-content")

    result = server.upload_document(
        file_path=str(file_path),
        metadata={"title": "Invoice", "tags": [1, 2], "custom": {"foo": "bar"}},
        filename="upload.pdf",
    )

    assert result["task_id"] == "abc123"
    assert captured["url"] == "http://localhost:8000/api/documents/post_document/"
    assert captured["headers"]["Authorization"] == "Token test-token"

    data = captured["data"]
    assert ("title", "Invoice") in data
    assert ("tags", "1") in data
    assert ("tags", "2") in data
    custom_values = [value for key, value in data if key == "custom"]
    assert custom_values
    assert json.loads(custom_values[0]) == {"foo": "bar"}

    files = captured["files"]["document"]
    assert files[0] == "upload.pdf"
    assert files[2] == "application/octet-stream"


def test_upload_document_missing_file() -> None:
    result = server.upload_document(file_path="/no/such/file.pdf")
    assert result["error"] == "file_not_found"


def test_get_document_calls_endpoint(monkeypatch) -> None:
    captured: dict[str, object] = {}
    payload = {"id": 321, "title": "Fetched"}

    class _GetClient:
        def __init__(self, payload: dict[str, object], captured: dict[str, object]) -> None:
            self._payload = payload
            self._captured = captured

        def __enter__(self) -> "_GetClient":
            return self

        def __exit__(self, *_: object) -> bool:
            return False

        def get(self, url: str, *, headers: dict[str, str]) -> _DummyResponse:
            self._captured["url"] = url
            self._captured["headers"] = headers
            return _DummyResponse(self._payload)

    def fake_client(*, timeout: float, verify: bool | str) -> _GetClient:
        return _GetClient(payload, captured)

    monkeypatch.setattr(server.httpx, "Client", fake_client)
    monkeypatch.setenv("PAPERLESS_URL", "http://localhost:8000")
    monkeypatch.setenv("PAPERLESS_TOKEN", "test-token")
    monkeypatch.setenv("PAPERLESS_VERIFY_SSL", "false")
    monkeypatch.setenv("MCP_LOG_LEVEL", "INFO")

    result = server.get_document(321)

    assert result["id"] == 321
    assert captured["url"] == "http://localhost:8000/api/documents/321/"


def test_update_document_patches_payload(monkeypatch) -> None:
    captured: dict[str, object] = {}
    payload = {"id": 123, "title": "Updated"}

    class _UpdateClient:
        def __init__(self, payload: dict[str, object], captured: dict[str, object]) -> None:
            self._payload = payload
            self._captured = captured

        def __enter__(self) -> "_UpdateClient":
            return self

        def __exit__(self, *_: object) -> bool:
            return False

        def patch(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> _DummyResponse:
            self._captured["url"] = url
            self._captured["headers"] = headers
            self._captured["json"] = json
            return _DummyResponse(self._payload)

    def fake_client(*, timeout: float, verify: bool | str) -> _UpdateClient:
        return _UpdateClient(payload, captured)

    monkeypatch.setattr(server.httpx, "Client", fake_client)
    monkeypatch.setenv("PAPERLESS_URL", "http://localhost:8000")
    monkeypatch.setenv("PAPERLESS_TOKEN", "test-token")
    monkeypatch.setenv("PAPERLESS_VERIFY_SSL", "false")
    monkeypatch.setenv("MCP_LOG_LEVEL", "INFO")

    result = server.update_document(
        document_id=123,
        updates={"title": "Updated", "tags": [1, 2], "correspondent": None},
    )

    assert result["id"] == 123
    assert captured["url"] == "http://localhost:8000/api/documents/123/"
    assert captured["json"] == {"title": "Updated", "tags": [1, 2], "correspondent": None}
