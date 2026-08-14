"""Smoke-test the API surface without starting external services."""

import unittest

from app.main import app


class ApiContractTests(unittest.TestCase):
    def test_critical_routes_are_registered(self) -> None:
        # FastAPI 0.137+ keeps included routers lazy, so OpenAPI is the stable
        # public representation of the fully expanded route table.
        paths = app.openapi()["paths"]
        routes = {
            (path, method.upper())
            for path, operations in paths.items()
            for method in operations
        }
        expected = {
            ("/api/health", "GET"),
            ("/api/auth/login", "POST"),
            ("/api/auth/register", "POST"),
            ("/api/auth/me", "GET"),
            ("/api/deals", "GET"),
            ("/api/deals", "POST"),
            ("/api/deals/{deal_id}", "GET"),
            ("/api/deals/{deal_id}", "PATCH"),
            ("/api/deals/{deal_id}", "DELETE"),
            ("/api/deals/{deal_id}/sections", "GET"),
            ("/api/deals/{deal_id}/documents", "GET"),
        }
        missing = expected - routes
        self.assertFalse(missing, f"Missing critical API routes: {sorted(missing)}")

    def test_openapi_schema_can_be_generated(self) -> None:
        schema = app.openapi()
        self.assertEqual(schema["info"]["title"], "Credit Dossier API")
        self.assertEqual(schema["info"]["version"], "2.0.0")
        self.assertIn("/api/deals", schema["paths"])


if __name__ == "__main__":
    unittest.main()
