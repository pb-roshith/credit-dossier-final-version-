import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.mcp_service import MCPClientService
from app.services.mistral_library_service import MistralLibraryService


class ReturnValueChecksTests(unittest.TestCase):
    def test_library_delete_reports_success(self):
        client = MagicMock()
        client.beta.libraries.delete_async = AsyncMock(return_value=None)
        with patch(
            "app.services.mistral_library_service._get_client", return_value=client
        ):
            deleted = asyncio.run(MistralLibraryService.delete_library("library-1"))
        self.assertTrue(deleted)

    def test_library_delete_reports_failure(self):
        client = MagicMock()
        client.beta.libraries.delete_async = AsyncMock(side_effect=RuntimeError("failed"))
        with patch(
            "app.services.mistral_library_service._get_client", return_value=client
        ):
            deleted = asyncio.run(MistralLibraryService.delete_library("library-1"))
        self.assertFalse(deleted)

    def test_mcp_connect_reports_failure(self):
        original_connected = MCPClientService.is_connected
        try:
            with patch(
                "app.services.mcp_service.sse_client",
                side_effect=RuntimeError("unavailable"),
            ):
                connected = asyncio.run(MCPClientService.connect())
            self.assertFalse(connected)
            self.assertFalse(MCPClientService.is_connected)
        finally:
            MCPClientService.is_connected = original_connected


if __name__ == "__main__":
    unittest.main()
