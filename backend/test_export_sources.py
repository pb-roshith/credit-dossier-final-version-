"""Exported narratives must not expose internal source markers."""

import unittest
from types import SimpleNamespace

from app.services.export_service import _section_narrative
from app.services.mistral_library_service import (
    clean_generation_artifacts,
    conversation_output_content,
    normalize_inline_sources,
    repair_inline_source_markers,
)


class ExportSourceTests(unittest.TestCase):
    def test_conversation_tool_references_become_inline_sources(self) -> None:
        response = SimpleNamespace(
            outputs=[
                SimpleNamespace(type="tool.execution"),
                SimpleNamespace(
                    type="message.output",
                    content=[
                        SimpleNamespace(type="text", text="Revenue increased."),
                        SimpleNamespace(
                            type="tool_reference",
                            title="Annual_Report.pdf",
                        ),
                    ],
                ),
            ]
        )
        self.assertEqual(
            conversation_output_content(response),
            "Revenue increased. [Source : Annual_Report.pdf]",
        )

    def test_internal_search_query_is_removed(self) -> None:
        content, leaked = clean_generation_artifacts(
            "Relationship established in 2012.\n"
            '{"query": "banking relationship vintage ABCC"}'
        )
        self.assertTrue(leaked)
        self.assertEqual(content, "Relationship established in 2012.")

    def test_split_postgres_source_is_repaired_inline(self) -> None:
        content = (
            "Relationship established in 2012\n"
            " : PostgreSQL.credit_dossier.section3a_customer_facilities.\n"
            "Next paragraph."
        )
        self.assertEqual(
            repair_inline_source_markers(content),
            "Relationship established in 2012 "
            "[Source : PostgreSQL.credit_dossier.section3a_customer_facilities]"
            "\nNext paragraph.",
        )

    def test_duplicate_adjacent_sources_are_collapsed(self) -> None:
        self.assertEqual(
            repair_inline_source_markers(
                "Fact. [Source : Report.pdf] [Source : Report.pdf]"
            ),
            "Fact. [Source : Report.pdf]",
        )

    def test_legacy_references_are_normalized_for_the_editor(self) -> None:
        content = (
            "Revenue increased.[1] Margin improved.[2]\n\n"
            "## References\n"
            "[1] [[Annual_Report.pdf]], page 12\n"
            "[2] [[Financial_Statements.pdf]], page 8"
        )
        self.assertEqual(
            normalize_inline_sources(content),
            "Revenue increased. [Source : Annual_Report.pdf] "
            "Margin improved. [Source : Financial_Statements.pdf]",
        )

    def test_inline_source_markers_are_removed(self) -> None:
        section = SimpleNamespace(
            final_generated_content=(
                "Revenue increased by 12%. [Source : Annual_Report.pdf]\n\n"
                "Leverage improved. [Source: PostgreSQL.credit_balance_sheet]"
            ),
            generated_content=None,
        )
        self.assertEqual(
            _section_narrative(section),
            "Revenue increased by 12%.\n\nLeverage improved.",
        )

    def test_legacy_reference_section_is_removed(self) -> None:
        section = SimpleNamespace(
            final_generated_content=(
                "Revenue increased.[1]\n\n"
                "## References\n"
                "[1] [[Annual_Report.pdf]], page 12"
            ),
            generated_content=None,
        )
        self.assertEqual(_section_narrative(section), "Revenue increased.")


if __name__ == "__main__":
    unittest.main()
