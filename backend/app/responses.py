"""Explicit encoding for JSON responses, including centralized error responses."""

from starlette.responses import JSONResponse


class Utf8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"

    def init_headers(self, headers=None) -> None:
        super().init_headers(headers)
        self.headers["X-Content-Type-Options"] = "nosniff"
