"""Fast, offline checks for the local MCP catalog and PDF generator."""

import unittest
import json
import io
from unittest.mock import patch

from catalog import (
    PDF_FILES,
    TABLE_NAMES,
    build_company_context,
    document_sections,
    table_seed_rows,
)
from manufacture import create_pdf_payloads, write_pdf
import server


class LocalMCPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = build_company_context(
            "Test Manufacturing Limited",
            "Industrial manufacturing",
            "Pune, India",
        )

    def test_catalog_counts(self) -> None:
        rows = table_seed_rows(self.context)
        self.assertEqual(len(PDF_FILES), 17)
        self.assertEqual(len(TABLE_NAMES), 16)
        self.assertEqual(set(rows), set(TABLE_NAMES))
        self.assertTrue(all(rows[table_name] for table_name in TABLE_NAMES))
        self.assertGreaterEqual(sum(len(table_rows) for table_rows in rows.values()), 100)
        self.assertTrue(
            all(
                len(document_sections(filename, self.context)) >= 5
                for filename in PDF_FILES
            )
        )

    def test_pdf_generation(self) -> None:
        payloads = create_pdf_payloads(self.context)
        self.assertEqual(len(payloads), 17)
        self.assertTrue(all(data.startswith(b"%PDF") for data in payloads.values()))
        self.assertTrue(all(len(data) > 4_000 for data in payloads.values()))

    def test_wide_ai_table_is_split_and_constrained(self) -> None:
        long_value = "Detailed legal case narrative and supporting facts. " * 30

        class WideTableGenerator:
            def generate_document(self, filename, context):
                return {
                    "title": "Legal Proceedings",
                    "document_summary": "Synthetic legal case details.",
                    "sections": [
                        {
                            "heading": "Civil proceedings",
                            "paragraphs": ["Detailed synthetic testing data."],
                            "table": [
                                [f"Column {number}" for number in range(7)],
                                *[
                                    [f"Case ID: CIV/2024/{row}", *([long_value] * 6)]
                                    for row in range(5)
                                ],
                            ],
                        }
                    ],
                }

        buffer = io.BytesIO()
        write_pdf(buffer, "Legal_Proceedings.pdf", self.context, WideTableGenerator())
        self.assertTrue(buffer.getvalue().startswith(b"%PDF"))

    def test_company_dropdown_is_scoped_to_owner(self) -> None:
        company = {
            "name": "Private Client Limited",
            "industry": "Manufacturing",
            "geography": "India",
            "segment": "Mid Corporate",
            "kyc_status": "Verified",
            "mistral_library_id": "lib_test",
            "document_count": 17,
        }
        with patch.object(server, "db_list_companies", return_value=[company]) as listing:
            payload = json.loads(server.list_companies("user-1"))
        listing.assert_called_once_with("user-1")
        self.assertEqual(payload["companies"][0]["name"], company["name"])
        self.assertEqual(payload["companies"][0]["document_count"], 17)
        self.assertEqual(payload["companies"][0]["data_source"], "manufactured")


if __name__ == "__main__":
    unittest.main()
