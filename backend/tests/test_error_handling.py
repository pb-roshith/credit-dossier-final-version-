import unittest
from unittest.mock import MagicMock, patch

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, OperationalError

from app.database import get_db
from app.error_handlers import install_exception_handlers


class DatabaseSessionCleanupTests(unittest.TestCase):
    def test_database_failure_rolls_back_and_always_closes(self):
        session = MagicMock()
        with patch("app.database.SessionLocal", return_value=session):
            dependency = get_db()
            self.assertIs(next(dependency), session)
            error = OperationalError("SELECT 1", {}, RuntimeError("offline"))
            with self.assertRaises(OperationalError):
                dependency.throw(error)
        session.rollback.assert_called_once_with()
        session.close.assert_called_once_with()

    def test_non_database_failure_also_rolls_back_and_closes(self):
        session = MagicMock()
        with patch("app.database.SessionLocal", return_value=session):
            dependency = get_db()
            next(dependency)
            with self.assertRaises(RuntimeError):
                dependency.throw(RuntimeError("request failed"))
        session.rollback.assert_called_once_with()
        session.close.assert_called_once_with()


class ExceptionResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = FastAPI()
        install_exception_handlers(app)

        @app.get("/database")
        def database_failure():
            raise OperationalError("SELECT secret", {}, RuntimeError("password=secret"))

        @app.get("/timeout")
        def timeout_failure():
            raise httpx.ConnectTimeout("private upstream details")

        @app.get("/integrity")
        def integrity_failure():
            raise IntegrityError("INSERT secret", {}, RuntimeError("duplicate secret"))

        @app.get("/unexpected")
        def unexpected_failure():
            raise RuntimeError("private implementation details")

        @app.get("/expected-http")
        def expected_http_failure():
            raise HTTPException(status_code=409, detail="Expected conflict")

        @app.get("/validated")
        def validated(number: int):
            return {"number": number}

        cls.client = TestClient(app, raise_server_exceptions=False)

    def test_database_error_is_specific_and_sanitized(self):
        response = self.client.get("/database")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error_code"], "DB-003")
        self.assertEqual(
            response.json()["detail"],
            "The database is temporarily unavailable. Please try again.",
        )
        self.assertTrue(response.json()["event_id"])
        self.assertNotIn("secret", response.text)

    def test_upstream_timeout_is_specific_and_sanitized(self):
        response = self.client.get("/timeout")
        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.json()["error_code"], "EXT-001")
        self.assertNotIn("private", response.text)

    def test_integrity_error_is_reported_as_a_conflict(self):
        response = self.client.get("/integrity")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error_code"], "DB-001")
        self.assertEqual(response.json()["detail"], "The request conflicts with existing data.")
        self.assertTrue(response.json()["event_id"])
        self.assertNotIn("secret", response.text)

    def test_unexpected_error_uses_sanitized_final_boundary(self):
        response = self.client.get("/unexpected")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error_code"], "SYS-001")
        self.assertEqual(response.json()["detail"], "An unexpected server error occurred.")
        self.assertNotIn("private", response.text)

    def test_framework_http_exception_receives_a_catalog_code(self):
        response = self.client.get("/expected-http")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error_code"], "STATE-001")
        self.assertEqual(
            response.json()["detail"],
            "The operation conflicts with the current resource state.",
        )

    def test_request_validation_receives_a_catalog_code(self):
        response = self.client.get("/validated", params={"number": "not-a-number"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error_code"], "REQ-001")
        self.assertNotIn("not-a-number", response.text)

    def test_framework_404_receives_a_catalog_code(self):
        response = self.client.get("/missing")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error_code"], "RESOURCE-001")
        self.assertTrue(response.json()["event_id"])


if __name__ == "__main__":
    unittest.main()
