"""
HTTP metrics middleware for SLI/SLO monitoring.

This middleware tracks request count and duration for all HTTP endpoints
(except those in METRICS_DENY_LIST) to enable availability and latency SLIs.

Endpoints are labelled with FastAPI's scope["route"].path. Requests matching
no route are not recorded: labelling them by raw path would let bots create
unbounded label values.
"""

import time
from types import TracebackType

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from polar.observability.http_metrics import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUEST_TOTAL,
)
from polar.observability.utils import get_path_template

POLAR_PACKAGE_PREFIX = "polar."


def describe_exception(exc: BaseException) -> str:
    """
    Name an unhandled exception for the `exception` metric label.

    The innermost frame in the polar package is where polar code handed
    control to the failing call, e.g.
    "IntegrityError in polar.subscription.service:update_product".
    Without a polar frame, only the type is given.
    """
    name = type(exc).__name__
    site = None

    tb: TracebackType | None = exc.__traceback__
    while tb is not None:
        frame = tb.tb_frame
        module = frame.f_globals.get("__name__", "")
        # This middleware's own frame is on every traceback; skip it.
        if module.startswith(POLAR_PACKAGE_PREFIX) and module != __name__:
            site = f"{module}:{frame.f_code.co_name}"
        tb = tb.tb_next

    if site is None:
        return name

    return f"{name} in {site}"


class HttpMetricsMiddleware:
    """
    ASGI middleware that records HTTP metrics for all endpoints.

    Metrics are recorded in the finally block after the request completes,
    which ensures scope["route"] is populated by FastAPI's routing.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.perf_counter()
        status_code = "500"  # Default in case of unhandled exception
        exception = ""

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = str(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            exception = describe_exception(exc)
            raise
        finally:
            # Route is now populated by FastAPI (after routing completed)
            path_template = get_path_template(scope)
            # None: excluded app, deny-listed path, or no route matched
            if path_template is not None:
                duration = time.perf_counter() - start_time
                method = scope.get("method", "UNKNOWN")
                state = scope.get("state", {})
                api_version = str(state.get("api_version", ""))
                api_version_set = str(state.get("api_version_set", False)).lower()

                HTTP_REQUEST_TOTAL.labels(
                    endpoint=path_template,
                    method=method,
                    status_code=status_code,
                    api_version=api_version,
                    api_version_set=api_version_set,
                    exception=exception,
                ).inc()

                HTTP_REQUEST_DURATION_SECONDS.labels(
                    endpoint=path_template,
                    method=method,
                    api_version=api_version,
                    api_version_set=api_version_set,
                ).observe(duration)
