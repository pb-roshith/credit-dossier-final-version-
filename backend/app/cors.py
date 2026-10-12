"""CORS preflights limited to the methods registered for the requested path."""

from fastapi.routing import iter_route_contexts
from starlette.datastructures import Headers
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import PlainTextResponse
from starlette.routing import Match


class RouteCORSMiddleware(CORSMiddleware):
    def __init__(self, app, *, router, **kwargs):
        if "*" in kwargs.get("allow_origins", ()):
            raise ValueError("CORS requires explicit trusted origins.")
        super().__init__(app, **kwargs)
        self.router = router

    def allowed_route_methods(self, scope):
        def matched_methods(candidate_scope):
            methods = set()
            for route in iter_route_contexts(self.router.routes):
                match, _ = route.matches(candidate_scope)
                if match in (Match.FULL, Match.PARTIAL):
                    methods.update(getattr(route, "methods", None) or ())
            return methods

        methods = matched_methods(scope)
        # Mirror the router's slash redirect without redirecting OPTIONS requests.
        # Browsers may reject redirects during CORS preflight.
        path = scope["path"]
        if not methods and self.router.redirect_slashes and path != "/":
            redirected_scope = dict(scope)
            redirected_scope["path"] = path.rstrip("/") if path.endswith("/") else path + "/"
            methods = matched_methods(redirected_scope)
        return methods.intersection(self.allow_methods)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await super().__call__(scope, receive, send)
        headers = Headers(scope=scope)
        if scope["method"] != "OPTIONS" or "origin" not in headers or "access-control-request-method" not in headers:
            return await super().__call__(scope, receive, send)

        # Retain Starlette's exact-origin and request-header checks.
        response = self.preflight_response(headers)
        if response.status_code < 400:
            methods = self.allowed_route_methods(scope)
            if headers["access-control-request-method"] not in methods:
                response = PlainTextResponse("Disallowed CORS method", status_code=400)
            else:
                response.headers["Access-Control-Allow-Methods"] = ", ".join(sorted(methods))

        # Do not advertise permissions for rejected origins, headers, or methods.
        if response.status_code >= 400:
            for name in list(response.headers):
                if name.lower().startswith("access-control-"):
                    del response.headers[name]
        response.headers["Cache-Control"] = "no-store"
        response.headers["Vary"] = "Origin, Access-Control-Request-Method, Access-Control-Request-Headers, Access-Control-Request-Private-Network"
        await response(scope, receive, send)
