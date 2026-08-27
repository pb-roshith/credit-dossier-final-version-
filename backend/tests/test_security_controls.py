import base64
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.security as security
from app.report_security import safe_export_filename, secure_download_headers
from app.request_security import install_request_security_middleware


class SecurityControlTests(unittest.TestCase):
    def setUp(self):
        self.key = base64.urlsafe_b64encode(b"k" * 32).decode("ascii")

    def test_tokenization_is_keyed_stable_and_non_reversible(self):
        with patch.object(security.settings, "REPORT_TOKENIZATION_KEY", self.key):
            with patch.object(security, "_cached_key", None):
                first = security.tokenize_sensitive_value("ABCDE1234F", "pan")
                second = security.tokenize_sensitive_value("ABCDE1234F", "pan")
                other = security.tokenize_sensitive_value("ABCDE1234G", "pan")
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertNotIn("ABCDE1234F", first)

    def test_report_masking_removes_recognized_identifiers(self):
        source = "Email alice@example.com, PAN ABCDE1234F, account number 12345678901"
        with patch.object(security.settings, "REPORT_TOKENIZATION_KEY", self.key):
            with patch.object(security, "_cached_key", None):
                masked = security.mask_sensitive_text(source)
        self.assertNotIn("alice@example.com", masked)
        self.assertNotIn("ABCDE1234F", masked)
        self.assertNotIn("12345678901", masked)
        self.assertGreaterEqual(masked.count("[MASKED:tok_"), 3)

    def test_get_request_bodies_are_rejected_and_post_is_allowed(self):
        app = FastAPI()
        install_request_security_middleware(app)

        @app.api_route("/data", methods=["GET", "POST"])
        def data():
            return {"ok": True}

        client = TestClient(app)
        rejected = client.request("GET", "/data", content=b'{"secret":"value"}')
        rejected_query = client.get("/data?secret=value")
        accepted = client.post("/data", json={"secret": "value"})
        self.assertEqual(rejected.status_code, 405)
        self.assertEqual(rejected_query.status_code, 405)
        self.assertEqual(rejected.headers["allow"], "POST")
        self.assertEqual(accepted.status_code, 200)

    def test_report_headers_disable_caching_and_sanitize_filename(self):
        filename = safe_export_filename('Acme\r\nX-Evil: yes', "PitchBook", "pdf")
        headers = secure_download_headers(filename)
        self.assertNotIn("\r", headers["Content-Disposition"])
        self.assertNotIn("\n", headers["Content-Disposition"])
        self.assertIn("no-store", headers["Cache-Control"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")


if __name__ == "__main__":
    unittest.main()
