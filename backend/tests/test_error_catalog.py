import re
import unittest
from pathlib import Path

from app.error_catalog import ERROR_CATALOG, resolve_http_error_code


class ErrorCatalogTests(unittest.TestCase):
    def test_codes_and_messages_are_unique_and_well_formed(self):
        codes = list(ERROR_CATALOG)
        messages = [definition.message for definition in ERROR_CATALOG.values()]

        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(len(messages), len(set(messages)))
        for code, definition in ERROR_CATALOG.items():
            self.assertEqual(code, definition.code)
            self.assertRegex(code, re.compile(r"^[A-Z]+-\d{3}$"))
            self.assertGreaterEqual(definition.http_status, 400)
            self.assertLess(definition.http_status, 600)

    def test_published_code_book_contains_every_runtime_code(self):
        code_book = (Path(__file__).parents[2] / "error_codes.md").read_text(encoding="utf-8")
        for code in ERROR_CATALOG:
            self.assertIn(f"`{code}`", code_book)

    def test_legacy_http_errors_are_mapped_without_exposing_detail(self):
        self.assertEqual(resolve_http_error_code(401, "private token contents"), "AUTH-003")
        self.assertEqual(resolve_http_error_code(400, "Unsupported file extension: .exe"), "FILE-001")
        self.assertEqual(resolve_http_error_code(500, "database password"), "SYS-001")


if __name__ == "__main__":
    unittest.main()
