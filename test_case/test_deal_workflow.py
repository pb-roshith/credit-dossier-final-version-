"""Core deal creation, visibility, editing, and deletion checks."""

from app.models import AuditEntry, Deal, Section
from app.services.deal_service import DEFAULT_SECTIONS, DealService
from test_case.support import DatabaseTestCase


class DealWorkflowTests(DatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.manager = self.create_user()
        self.deal_data = {
            "customer": "Test Manufacturing Limited",
            "customer_type": "Existing",
            "industry": "Manufacturing",
            "geography": "Pune",
            "facility": "Term Loan",
            "currency": "INR",
            "amount": 25_000_000,
            "tenure": 60,
        }

    def test_create_deal_builds_complete_default_dossier(self) -> None:
        deal = DealService.create_deal(self.db, self.deal_data, self.manager.id)

        sections = self.db.query(Section).filter_by(deal_id=deal.id).all()
        audits = self.db.query(AuditEntry).filter_by(deal_id=deal.id).all()
        self.assertTrue(deal.id.startswith("deal_"))
        self.assertEqual(deal.customer, self.deal_data["customer"])
        self.assertEqual(len(sections), len(DEFAULT_SECTIONS))
        self.assertEqual(
            [section.section_key for section in sorted(sections, key=lambda s: s.order_index)],
            [definition["section_key"] for definition in DEFAULT_SECTIONS],
        )
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].action, "deal.created")

    def test_deal_edit_visibility_status_and_delete(self) -> None:
        deal = DealService.create_deal(self.db, self.deal_data, self.manager.id)
        other_manager = self.create_user("other.manager")
        analyst = self.create_user("test.analyst", "credit_analyst")

        self.assertEqual([item.id for item in DealService.list_deals(self.db, self.manager)], [deal.id])
        self.assertEqual(DealService.list_deals(self.db, other_manager), [])
        self.assertEqual([item.id for item in DealService.list_deals(self.db, analyst)], [deal.id])

        updated = DealService.update_deal(self.db, deal.id, {"amount": 30_000_000})
        self.assertIsNotNone(updated)
        self.assertEqual(updated.amount, 30_000_000)

        section = self.db.query(Section).filter_by(deal_id=deal.id).first()
        DealService.update_section(self.db, section.id, {"state": "ready"})
        DealService.update_deal_status_from_sections(self.db, deal.id)
        self.assertEqual(self.db.get(Deal, deal.id).status, "In Progress")

        self.assertTrue(DealService.delete_deal(self.db, deal.id))
        self.assertIsNone(self.db.get(Deal, deal.id))
        self.assertFalse(DealService.delete_deal(self.db, deal.id))

