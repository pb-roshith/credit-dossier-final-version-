"""Fast, offline checks for the local MCP catalog and PDF generator."""

import unittest
import json
from unittest.mock import patch

from catalog import (
    PDF_FILES,
    TABLE_NAMES,
    build_company_context,
    document_sections,
    table_seed_rows,
)
from manufacture import create_pdf_payloads
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

    def test_registered_client_is_in_company_dropdown_payload(self) -> None:
        client = {
            "legal_name": "Real Client Limited",
            "industry": "Manufacturing",
            "geography": "India",
            "mistral_library_id": "lib_test",
        }
        documents = [
            {
                "document_name": "Annual Report.pdf",
                "document_url": "mistral://lib_test/doc_test",
                "summary": "Annual report",
                "status": "completed",
                "storage": "mistral_library",
            }
        ]
        with (
            patch.object(server, "db_list_companies", return_value=[]),
            patch.object(
                server,
                "db_list_registered_clients",
                return_value=[client],
            ),
            patch.object(
                server,
                "_list_registered_library_documents",
                return_value=documents,
            ),
        ):
            payload = json.loads(server.list_companies())
        self.assertEqual(payload["companies"][0]["name"], client["legal_name"])
        self.assertEqual(payload["companies"][0]["document_count"], 1)
        self.assertEqual(payload["companies"][0]["data_source"], "real_world")


if __name__ == "__main__":
    unittest.main()
