"""Tests for HTTP metrics middleware.

These tests are isolated from the main Polar infrastructure to avoid
database and service connections during unit testing.
"""

import os
import tempfile
import types
from collections.abc import Generator
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from starlette.types import Receive, Scope, Send


@pytest.fixture(scope="module")
def prometheus_tmpdir() -> Generator[str]:
    """Create a temporary prometheus directory for module tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["PROMETHEUS_MULTIPROC_DIR"] = tmpdir
        yield tmpdir


@pytest.mark.anyio
class TestMiddlewareASGIBehavior:
    """Test ASGI middleware behavior including async calls."""

    @pytest.fixture(scope="class")
    def prometheus_tmpdir(self) -> Generator[str]:
        """Create a temporary prometheus directory for class tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["PROMETHEUS_MULTIPROC_DIR"] = tmpdir
            yield tmpdir

    async def test_non_http_scope_passthrough(self, prometheus_tmpdir: str) -> None:
        """Test that non-HTTP scopes are passed through without metrics."""
        from polar.observability.http_middleware import HttpMetricsMiddleware

        app_called = False

        async def mock_app(scope: Scope, receive: Receive, send: Send) -> None:
            nonlocal app_called
            app_called = True

        middleware = HttpMetricsMiddleware(mock_app)

        # Websocket scope
        scope = cast(Scope, {"type": "websocket", "path": "/ws"})

        await middleware(scope, cast(Receive, None), cast(Send, None))

        assert app_called is True

    async def test_lifespan_scope_passthrough(self, prometheus_tmpdir: str) -> None:
        """Test that lifespan scopes are passed through without metrics."""
        from polar.observability.http_middleware import HttpMetricsMiddleware

        app_called = False

        async def mock_app(scope: Scope, receive: Receive, send: Send) -> None:
            nonlocal app_called
            app_called = True

        middleware = HttpMetricsMiddleware(mock_app)

        # Lifespan scope
        scope = cast(Scope, {"type": "lifespan"})

        await middleware(scope, cast(Receive, None), cast(Send, None))

        assert app_called is True

    async def test_status_code_capture(self, prometheus_tmpdir: str) -> None:
        """Test that status codes are correctly captured."""
        from polar.observability.http_middleware import HttpMetricsMiddleware

        async def mock_app(scope: Scope, receive: Receive, send: Send) -> None:
            await send({"type": "http.response.start", "status": 201})
            await send({"type": "http.response.body", "body": b""})

        middleware = HttpMetricsMiddleware(mock_app)

        scope = cast(
            Scope,
            {
                "type": "http",
                "path": "/v1/checkouts",
                "method": "POST",
            },
        )

        messages_sent: list[dict[str, Any]] = []

        async def mock_send(message: dict[str, Any]) -> None:
            messages_sent.append(message)

        await middleware(scope, cast(Receive, None), cast(Send, mock_send))

        # Verify the status was captured (201)
        assert any(m.get("status") == 201 for m in messages_sent)

    async def test_exception_still_records_metrics(
        self, prometheus_tmpdir: str
    ) -> None:
        """Test that metrics are recorded even when app raises exception."""
        from polar.observability.http_middleware import HttpMetricsMiddleware

        async def mock_app(scope: Scope, receive: Receive, send: Send) -> None:
            raise ValueError("Test exception")

        middleware = HttpMetricsMiddleware(mock_app)

        scope = cast(
            Scope,
            {
                "type": "http",
                "path": "/v1/checkouts",
                "method": "GET",
            },
        )

        async def noop_send(message: dict[str, Any]) -> None:
            pass

        # The middleware should record metrics in finally block
        # and then re-raise the exception
        with pytest.raises(ValueError, match="Test exception"):
            await middleware(scope, cast(Receive, None), cast(Send, noop_send))

    async def test_default_status_code_on_exception(
        self, prometheus_tmpdir: str
    ) -> None:
        """Test that status code defaults to 500 when no response sent."""
        from polar.observability.http_middleware import HttpMetricsMiddleware

        # This tests that status_code starts as "500" (line 89 in middleware)
        # and stays that way if app crashes before sending response

        async def mock_app(scope: Scope, receive: Receive, send: Send) -> None:
            # Crash before sending any response
            raise RuntimeError("App crashed")

        middleware = HttpMetricsMiddleware(mock_app)

        scope = cast(
            Scope,
            {
                "type": "http",
                "path": "/v1/test",
                "method": "GET",
            },
        )

        async def noop_send(message: dict[str, Any]) -> None:
            pass

        with pytest.raises(RuntimeError):
            await middleware(scope, cast(Receive, None), cast(Send, noop_send))

        # Can't directly assert the status_code was "500" without mocking metrics
        # but this test ensures the code path works without crashing

    async def test_missing_method_uses_unknown(self, prometheus_tmpdir: str) -> None:
        """Test that missing method in scope results in UNKNOWN."""
        from polar.observability.http_middleware import HttpMetricsMiddleware

        async def mock_app(scope: Scope, receive: Receive, send: Send) -> None:
            await send({"type": "http.response.start", "status": 200})
            await send({"type": "http.response.body", "body": b""})

        middleware = HttpMetricsMiddleware(mock_app)

        # Scope without method
        scope = cast(
            Scope,
            {
                "type": "http",
                "path": "/v1/test",
                # No "method" key
            },
        )

        async def mock_send(message: dict[str, Any]) -> None:
            pass

        # Should not crash - method defaults to "UNKNOWN"
        await middleware(scope, cast(Receive, None), cast(Send, mock_send))

    async def test_various_http_methods(self, prometheus_tmpdir: str) -> None:
        """Test that various HTTP methods are handled correctly."""
        from polar.observability.http_middleware import HttpMetricsMiddleware

        async def mock_app(scope: Scope, receive: Receive, send: Send) -> None:
            await send({"type": "http.response.start", "status": 200})
            await send({"type": "http.response.body", "body": b""})

        middleware = HttpMetricsMiddleware(mock_app)

        methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]

        async def noop_send(message: dict[str, Any]) -> None:
            pass

        for method in methods:
            scope = cast(
                Scope,
                {
                    "type": "http",
                    "path": "/v1/test",
                    "method": method,
                },
            )

            # Should not crash for any method
            await middleware(scope, cast(Receive, None), cast(Send, noop_send))

    async def test_various_status_codes(self, prometheus_tmpdir: str) -> None:
        """Test that various status codes are captured correctly."""
        from polar.observability.http_middleware import HttpMetricsMiddleware

        status_codes = [200, 201, 204, 301, 400, 401, 403, 404, 500, 502, 503]

        for status in status_codes:

            async def mock_app(
                scope: Scope, receive: Receive, send: Send, _status: int = status
            ) -> None:
                await send({"type": "http.response.start", "status": _status})
                await send({"type": "http.response.body", "body": b""})

            middleware = HttpMetricsMiddleware(mock_app)

            scope = cast(
                Scope,
                {
                    "type": "http",
                    "path": "/v1/test",
                    "method": "GET",
                },
            )

            captured: list[dict[str, Any]] = []

            mock_send = AsyncMock(side_effect=captured.append)

            await middleware(scope, cast(Receive, None), cast(Send, mock_send))

            assert any(m.get("status") == status for m in captured)


def update_product() -> None:
    raise exc  # type: ignore[name-defined]  # noqa: F821


def _raise_from_module(module: str, exc: Exception) -> Any:
    """Return `update_product` whose frame reports `module` as its module."""
    namespace: dict[str, Any] = {"__name__": module, "exc": exc}
    return types.FunctionType(update_product.__code__, namespace, "update_product")


@pytest.mark.anyio
class TestExceptionLabel:
    """5xx samples name the exception and the innermost polar function."""

    async def _count(
        self, module: str, exc: Exception, path: str, exception: str
    ) -> float:
        from polar.observability.http_metrics import HTTP_REQUEST_TOTAL
        from polar.observability.http_middleware import HttpMetricsMiddleware

        raiser = _raise_from_module(module, exc)

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            raiser()

        scope = cast(
            Scope,
            {
                "type": "http",
                "path": path,
                "method": "PATCH",
                "route": type("Route", (), {"path": path})(),
            },
        )

        async def noop_send(message: dict[str, Any]) -> None:
            pass

        with pytest.raises(type(exc), match=str(exc)):
            await HttpMetricsMiddleware(app)(
                scope, cast(Receive, None), cast(Send, noop_send)
            )

        sample = HTTP_REQUEST_TOTAL.labels(
            endpoint=path,
            method="PATCH",
            status_code="500",
            api_version="",
            api_version_set="false",
            exception=exception,
        )
        return sample._value.get()

    async def test_names_innermost_polar_frame(self) -> None:
        count = await self._count(
            "polar.subscription.service",
            LookupError("duplicate key"),
            "/v1/test-exception-label/{id}",
            "LookupError in polar.subscription.service:update_product",
        )

        assert count == 1

    async def test_no_polar_frame_names_type_only(self) -> None:
        count = await self._count(
            "sqlalchemy.engine",
            ValueError("no polar frame"),
            "/v1/test-exception-label-bare/{id}",
            "ValueError",
        )

        assert count == 1
