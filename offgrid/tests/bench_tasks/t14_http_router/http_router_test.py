"""
Tests for the HTTP router system.

Covers:
  - Exact route matching
  - Parameterized route matching and extraction
  - Wildcard route matching
  - Route priority (exact > param > wildcard)
  - Middleware chain execution order
  - Middleware short-circuiting
  - Full integration (router + middleware + handler)
"""

import pytest
from router import Router, Route, MatchResult
from middleware import MiddlewareChain
from handler import Request, Response, make_handler, not_found


# ---------------------------------------------------------------------------
# Router: basic matching
# ---------------------------------------------------------------------------

class TestRouterBasic:
    def test_exact_match(self):
        router = Router()
        router.get("/users", lambda r: "users")
        result = router.match("GET", "/users")
        assert result is not None
        assert result.route.pattern == "/users"

    def test_no_match(self):
        router = Router()
        router.get("/users", lambda r: "users")
        assert router.match("GET", "/posts") is None

    def test_method_mismatch(self):
        router = Router()
        router.get("/users", lambda r: "users")
        assert router.match("POST", "/users") is None

    def test_root_path(self):
        router = Router()
        router.get("/", lambda r: "root")
        result = router.match("GET", "/")
        assert result is not None
        assert result.params == {}


# ---------------------------------------------------------------------------
# Router: parameter extraction
# ---------------------------------------------------------------------------

class TestRouterParams:
    def test_single_param(self):
        """Extract a single path parameter."""
        router = Router()
        router.get("/users/:id", lambda r: "user")
        result = router.match("GET", "/users/42")
        assert result is not None
        assert result.params == {"id": "42"}

    def test_multiple_params(self):
        """Extract multiple path parameters from nested route."""
        router = Router()
        router.get("/users/:id/posts/:post_id", lambda r: "post")
        result = router.match("GET", "/users/7/posts/99")
        assert result is not None
        assert result.params == {"id": "7", "post_id": "99"}

    def test_param_does_not_match_extra_segments(self):
        router = Router()
        router.get("/users/:id", lambda r: "user")
        assert router.match("GET", "/users/42/extra") is None


# ---------------------------------------------------------------------------
# Router: wildcard matching
# ---------------------------------------------------------------------------

class TestRouterWildcard:
    def test_wildcard_matches_subpath(self):
        router = Router()
        router.get("/static/*", lambda r: "static")
        result = router.match("GET", "/static/css/main.css")
        assert result is not None
        assert result.route.pattern == "/static/*"

    def test_wildcard_matches_single_segment(self):
        router = Router()
        router.get("/files/*", lambda r: "files")
        result = router.match("GET", "/files/readme.txt")
        assert result is not None


# ---------------------------------------------------------------------------
# Router: priority — exact > param > wildcard
# ---------------------------------------------------------------------------

class TestRouterPriority:
    def test_exact_beats_wildcard(self):
        """When both a wildcard and an exact route can match, exact wins."""
        router = Router()
        # Register wildcard FIRST — if the router just returns the first
        # match, this test will fail.
        router.get("/api/*", lambda r: "wildcard")
        router.get("/api/users", lambda r: "exact")

        result = router.match("GET", "/api/users")
        assert result is not None
        assert result.route.pattern == "/api/users"

    def test_param_beats_wildcard(self):
        """Parameterized route is more specific than wildcard."""
        router = Router()
        router.get("/api/*", lambda r: "wildcard")
        router.get("/api/:resource", lambda r: "param")

        result = router.match("GET", "/api/items")
        assert result is not None
        assert result.route.pattern == "/api/:resource"

    def test_exact_beats_param(self):
        """Exact route is more specific than parameterized."""
        router = Router()
        router.get("/api/:resource", lambda r: "param")
        router.get("/api/users", lambda r: "exact")

        result = router.match("GET", "/api/users")
        assert result is not None
        assert result.route.pattern == "/api/users"


# ---------------------------------------------------------------------------
# Middleware chain
# ---------------------------------------------------------------------------

class TestMiddleware:
    def test_single_middleware(self):
        chain = MiddlewareChain()
        log = []

        def mw(req, next_fn):
            log.append("before")
            resp = next_fn(req)
            log.append("after")
            return resp

        chain.use(mw)
        resp = chain.execute(
            Request(method="GET", path="/"),
            lambda req: Response(body="ok"),
        )
        assert resp.body == "ok"
        assert log == ["before", "after"]

    def test_middleware_order(self):
        """Middlewares execute in the order they were registered."""
        chain = MiddlewareChain()
        order = []

        def mw_a(req, next_fn):
            order.append("A-before")
            resp = next_fn(req)
            order.append("A-after")
            return resp

        def mw_b(req, next_fn):
            order.append("B-before")
            resp = next_fn(req)
            order.append("B-after")
            return resp

        def mw_c(req, next_fn):
            order.append("C-before")
            resp = next_fn(req)
            order.append("C-after")
            return resp

        chain.use(mw_a).use(mw_b).use(mw_c)

        resp = chain.execute(
            Request(method="GET", path="/"),
            lambda req: Response(body="done"),
        )
        assert order == [
            "A-before", "B-before", "C-before",
            "C-after", "B-after", "A-after",
        ]

    def test_middleware_short_circuit(self):
        """A middleware can return early without calling next_fn."""
        chain = MiddlewareChain()
        reached_handler = False

        def auth_mw(req, next_fn):
            if "token" not in req.headers:
                return Response(status=401, body="unauthorized")
            return next_fn(req)

        chain.use(auth_mw)

        def handler(req):
            nonlocal reached_handler
            reached_handler = True
            return Response(body="secret")

        resp = chain.execute(Request(method="GET", path="/", headers={}), handler)
        assert resp.status == 401
        assert not reached_handler

    def test_middleware_modifies_request(self):
        """Middleware can enrich the request before passing it along."""
        chain = MiddlewareChain()

        def inject_user(req, next_fn):
            req.context["user"] = "admin"
            return next_fn(req)

        chain.use(inject_user)

        def handler(req):
            return Response(body=f"hello {req.context['user']}")

        resp = chain.execute(Request(method="GET", path="/"), handler)
        assert resp.body == "hello admin"

    def test_no_middleware(self):
        chain = MiddlewareChain()
        resp = chain.execute(
            Request(method="GET", path="/"),
            lambda req: Response(body="direct"),
        )
        assert resp.body == "direct"


# ---------------------------------------------------------------------------
# Integration: Router + Middleware + Handler
# ---------------------------------------------------------------------------

class TestIntegration:
    def _dispatch(self, router, chain, method, path, headers=None):
        """Simulate dispatching a request through middleware + router."""
        req = Request(method=method, path=path, headers=headers or {})
        match = router.match(method, path)
        if match is None:
            return chain.execute(req, not_found)
        req.params = match.params
        return chain.execute(req, match.handler)

    def test_full_flow(self):
        router = Router()
        chain = MiddlewareChain()
        log = []

        def logging_mw(req, next_fn):
            log.append(f"{req.method} {req.path}")
            return next_fn(req)

        chain.use(logging_mw)

        router.get("/users/:id", lambda req: Response(body={"id": req.params["id"]}))

        resp = self._dispatch(router, chain, "GET", "/users/5")
        assert resp.body == {"id": "5"}
        assert log == ["GET /users/5"]

    def test_not_found_flow(self):
        router = Router()
        chain = MiddlewareChain()

        resp = self._dispatch(router, chain, "GET", "/nope")
        assert resp.status == 404

    def test_priority_with_middleware(self):
        router = Router()
        chain = MiddlewareChain()
        calls = []

        def track(req, next_fn):
            calls.append("mw")
            return next_fn(req)

        chain.use(track)

        router.get("/api/*", lambda req: Response(body="wildcard"))
        router.get("/api/health", lambda req: Response(body="exact"))

        resp = self._dispatch(router, chain, "GET", "/api/health")
        assert resp.body == "exact"
        assert calls == ["mw"]
