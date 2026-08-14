"""Narrative source handling and export-safety checks."""

import unittest
from types import SimpleNamespace

from app.services.export_service import _section_narrative
from app.services.mistral_library_service import (
    clean_generation_artifacts,
    normalize_inline_sources,
    repair_inline_source_markers,
)


class NarrativeExportTests(unittest.TestCase):
    def test_internal_generation_artifacts_are_removed(self) -> None:
        cleaned, leaked = clean_generation_artifacts(
            'Relationship established in 2012.\n{"query": "internal search"}'
        )
        self.assertTrue(leaked)
        self.assertEqual(cleaned, "Relationship established in 2012.")

    def test_legacy_references_become_inline_sources(self) -> None:
        content = (
            "Revenue increased.[1] Margin improved.[2]\n\n"
            "## References\n"
            "[1] [[Annual_Report.pdf]], page 12\n"
            "[2] [[Financial_Statements.pdf]], page 8"
        )
        normalized = normalize_inline_sources(content)
        self.assertIn("[Source : Annual_Report.pdf]", normalized)
        self.assertIn("[Source : Financial_Statements.pdf]", normalized)
        self.assertNotIn("## References", normalized)

    def test_split_and_duplicate_sources_are_repaired(self) -> None:
        repaired = repair_inline_source_markers(
            "Fact\n : Report.pdf. [Source : Report.pdf] [Source : Report.pdf]"
        )
        self.assertEqual(repaired.count("[Source : Report.pdf]"), 1)

    def test_exports_do_not_expose_internal_source_markers(self) -> None:
        section = SimpleNamespace(
            final_generated_content=(
                "Revenue increased. [Source : Annual_Report.pdf]\n\n"
                "Leverage improved. [Source: PostgreSQL.credit_balance_sheet]"
            ),
            generated_content=None,
        )
        exported = _section_narrative(section)
        self.assertEqual(exported, "Revenue increased.\n\nLeverage improved.")
        self.assertNotIn("Source", exported)


if __name__ == "__main__":
    unittest.main()

