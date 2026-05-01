"""
HTTP Router - supports exact, parameterized, and wildcard routes.

Routes are matched against incoming request paths with method filtering.
Supports:
  - Exact:     "/users"
  - Parameter: "/users/:id"
  - Wildcard:  "/static/*"
"""

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class Route:
    method: str
    pattern: str
    handler: Callable
    segments: list = field(default_factory=list)
    is_wildcard: bool = False
    param_names: list = field(default_factory=list)

    def __post_init__(self):
        self.segments = self.pattern.strip("/").split("/") if self.pattern != "/" else []
        self.is_wildcard = self.pattern.endswith("/*")
        self.param_names = [
            seg[1:] for seg in self.segments if seg.startswith(":")
        ]


@dataclass
class MatchResult:
    route: Route
    params: dict
    handler: Callable


class Router:
    def __init__(self):
        self._routes: list[Route] = []

    def add_route(self, method: str, pattern: str, handler: Callable) -> None:
        """Register a route with the given HTTP method and URL pattern."""
        route = Route(method=method.upper(), pattern=pattern, handler=handler)
        self._routes.append(route)

    def get(self, pattern: str, handler: Callable) -> None:
        self.add_route("GET", pattern, handler)

    def post(self, pattern: str, handler: Callable) -> None:
        self.add_route("POST", pattern, handler)

    def put(self, pattern: str, handler: Callable) -> None:
        self.add_route("PUT", pattern, handler)

    def delete(self, pattern: str, handler: Callable) -> None:
        self.add_route("DELETE", pattern, handler)

    def match(self, method: str, path: str) -> Optional[MatchResult]:
        """Find the best matching route for the given method and path.

        Returns a MatchResult with extracted parameters, or None if no match.
        """
        method = method.upper()
        path_segments = path.strip("/").split("/") if path != "/" else []

        for route in self._routes:
            if route.method != method:
                continue

            if route.is_wildcard:
                prefix = route.segments[:-1]  # everything before the "*"
                if len(path_segments) >= len(prefix):
                    if path_segments[: len(prefix)] == prefix:
                        params = self._extract_params(route, path_segments)
                        return MatchResult(
                            route=route, params=params, handler=route.handler
                        )
            else:
                if len(route.segments) != len(path_segments):
                    continue
                if self._segments_match(route.segments, path_segments):
                    params = self._extract_params(route, path_segments)
                    return MatchResult(
                        route=route, params=params, handler=route.handler
                    )

        return None

    def _segments_match(self, route_segments: list, path_segments: list) -> bool:
        """Check if route segments match path segments (params match anything)."""
        for i, seg in enumerate(route_segments):
            if seg.startswith(":"):
                continue  # parameter placeholder — matches any value
            if seg != path_segments[i]:
                return False
        return True

    def _extract_params(self, route: Route, path_segments: list) -> dict:
        """Extract named parameters from the path based on route pattern.

        Walks the route segments and picks out values at positions where
        the route has a ':name' placeholder.
        """
        params = {}
        for i, seg in enumerate(route.segments):
            if seg.startswith(":"):
                name = seg[1:]
                # grab the corresponding value from the actual path
                params[name] = path_segments[i + 1]
        return params
