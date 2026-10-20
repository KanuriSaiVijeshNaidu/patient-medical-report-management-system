import re
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_REQUEST_ID_REGEX = re.compile(r"^[0-9a-fA-F-]{36}$")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware that validates incoming X-Request-ID headers or generates a new UUIDv4,

    attaching it to request.state and outgoing response headers.
    """

    async def dispatch(self, request: Request, call_next):
        incoming_id = request.headers.get("x-request-id")
        if incoming_id and _REQUEST_ID_REGEX.match(incoming_id.strip()):
            request_id = incoming_id.strip()
        else:
            request_id = str(uuid.uuid4())

        request.state.request_id = request_id
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enforces security headers and cache-busting headers on sensitive endpoints."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"

        # Apply strict no-store cache control for sensitive medical data endpoints
        path = request.url.path
        if (
            path.startswith("/api/v1/access")
            or path.startswith("/api/v1/reports")
            or path.startswith("/api/v1/patients")
        ):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"

        return response


def get_request_id(request: Request) -> str:
    """Helper to extract request ID from request.state safely."""
    return getattr(request.state, "request_id", str(uuid.uuid4()))
