"""
Request / Response data classes and handler utilities for the HTTP router.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Request:
    """Represents an incoming HTTP request."""
    method: str
    path: str
    headers: dict = field(default_factory=dict)
    body: Any = None
    params: dict = field(default_factory=dict)
    context: dict = field(default_factory=dict)


@dataclass
class Response:
    """Represents an HTTP response."""
    status: int = 200
    body: Any = None
    headers: dict = field(default_factory=dict)

    def json(self, data: Any, status: int = 200) -> "Response":
        """Convenience: set body to data and content-type to JSON."""
        self.status = status
        self.body = data
        self.headers["Content-Type"] = "application/json"
        return self


def make_handler(status: int = 200, body: Any = None):
    """Factory that creates a simple handler returning a fixed response."""
    def handler(request: Request) -> Response:
        return Response(status=status, body=body or {"path": request.path})
    return handler


def error_response(status: int, message: str) -> Response:
    """Create an error response."""
    return Response(status=status, body={"error": message})


def not_found(request: Request) -> Response:
    return error_response(404, f"Not found: {request.path}")
