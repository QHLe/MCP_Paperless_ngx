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

    def __enter__(self) -> "_DummyClient":
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def get(self, url: str, *, headers: dict[str, str], params: dict[str, object]) -> _DummyResponse:
        self._captured["url"] = url
        self._captured["headers"] = headers
        self._captured["params"] = params
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
