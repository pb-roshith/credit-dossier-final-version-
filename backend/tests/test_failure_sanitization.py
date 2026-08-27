import asyncio
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app.models.user import AuditLog
from app.routers.admin import _sanitized_audit_response
from app.schemas.deal import _sanitize_failure_metadata
from app.services.mcp_service import MCPClientService


class FailureSanitizationTests(unittest.TestCase):
    def test_legacy_failure_metadata_is_sanitized_recursively(self):
        value = {
            "error": "password=secret",
            "nested": {"traceback": "C:/private/source.py:42"},
            "summary": "Accuracy assessment error: private upstream response",
        }
        sanitized = _sanitize_failure_metadata(value)
        rendered = str(sanitized)
        self.assertNotIn("secret", rendered)
        self.assertNotIn("source.py", rendered)
        self.assertNotIn("upstream response", rendered)

    def test_system_audit_api_response_hides_internal_fields(self):
        event = AuditLog(
            event_id="event-1",
            occurred_at=datetime.now(timezone.utc),
            category="system_error",
            event_type="python_error:private.module",
            status="error",
            source_ip="127.0.0.1",
            user_id="system",
            resource_id="private_file.py:99",
            http_status=500,
            message="SQL SELECT password FROM users",
        )
        response = _sanitized_audit_response(event)
        rendered = str(response.model_dump())
        self.assertNotIn("private", rendered)
        self.assertNotIn("password", rendered)
        self.assertEqual(response.event_type, "system_error")
        self.assertEqual(response.resource_id, "system")

    def test_mcp_failure_text_does_not_include_upstream_exception(self):
        original_open_until = MCPClientService._circuit_open_until
        try:
            MCPClientService._circuit_open_until = 0
            with patch.object(
                MCPClientService,
                "_call_tool",
                new=AsyncMock(side_effect=RuntimeError("token=secret")),
            ):
                result = asyncio.run(
                    MCPClientService.get_document_summaries("company", "owner")
                )
            self.assertEqual(result, "Document summaries are temporarily unavailable.")
            self.assertNotIn("secret", result)
        finally:
            MCPClientService._circuit_open_until = original_open_until


if __name__ == "__main__":
    unittest.main()
