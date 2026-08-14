"""Document ingestion, deduplication, and section-link checks."""

from app.models import DealDocument, SectionDocumentLink
from app.services.deal_service import DealService
from app.services.ingestion_service import IngestionService, extract_text_preview
from test_case.support import DatabaseTestCase


class DocumentWorkflowTests(DatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        manager = self.create_user()
        self.deal = DealService.create_deal(
            self.db,
            {
                "customer": "Document Test Limited",
                "industry": "Manufacturing",
                "geography": "Mumbai",
            },
            manager.id,
        )

    def test_plain_text_preview_preserves_content(self) -> None:
        content = b"Revenue grew 12%.\nDebt reduced."
        self.assertEqual(extract_text_preview(content, "financials.txt"), content.decode())

    async def _create_text_document(self):
        return await IngestionService.process_text_document(
            self.db,
            self.deal.id,
            "Revenue grew 12% and leverage improved.",
            note="Audited financial summary",
        )

    def test_text_ingestion_deduplicates_and_links_idempotently(self) -> None:
        import asyncio

        first = asyncio.run(self._create_text_document())
        second = asyncio.run(self._create_text_document())
        self.assertEqual(first.id, second.id)
        self.assertEqual(self.db.query(DealDocument).count(), 1)
        self.assertEqual(first.extraction_method, "plain_text")

        section_id = self.deal.sections[0].id
        first_links = IngestionService.link_documents_to_section(
            self.db, section_id, [first.id]
        )
        second_links = IngestionService.link_documents_to_section(
            self.db, section_id, [first.id]
        )
        self.assertEqual(first_links[0].id, second_links[0].id)
        self.assertEqual(self.db.query(SectionDocumentLink).count(), 1)

        self.assertTrue(
            IngestionService.unlink_document_from_section(self.db, section_id, first.id)
        )
        self.assertFalse(
            IngestionService.unlink_document_from_section(self.db, section_id, first.id)
        )

