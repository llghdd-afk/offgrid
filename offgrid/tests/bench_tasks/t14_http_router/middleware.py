"""
Middleware chain for HTTP request processing.

Each middleware is a callable that receives (request, next_fn) and can:
  - Modify the request before passing it along
  - Call next_fn(request) to continue the chain
  - Modify or replace the response returned by next_fn
  - Short-circuit by returning a response without calling next_fn
"""

from typing import Callable, Any


class MiddlewareChain:
    """Builds and executes an ordered chain of middleware functions."""

    def __init__(self):
        self._middlewares: list[Callable] = []

    def use(self, middleware: Callable) -> "MiddlewareChain":
        """Add a middleware to the chain. Returns self for chaining."""
        self._middlewares.append(middleware)
        return self

    def execute(self, request: Any, final_handler: Callable) -> Any:
        """Run the middleware chain, ending with final_handler.

        Each middleware signature: middleware(request, next_fn) -> response
        final_handler signature: final_handler(request) -> response
        """
        if not self._middlewares:
            return final_handler(request)

        chain = self._build_chain(final_handler)
        return chain(request)

    def _build_chain(self, final_handler: Callable) -> Callable:
        """Construct a nested chain of middleware calls.

        Iterates in reverse so the first registered middleware executes first.
        Each step wraps the previous next_fn with the current middleware.
        """
        next_fn = final_handler

        for middleware in reversed(self._middlewares):
            # Wrap: when called, invoke this middleware with the current next_fn
            def link(req, _next=next_fn):
                return middleware(req, _next)

            next_fn = link

        return next_fn
