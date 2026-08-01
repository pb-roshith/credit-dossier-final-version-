"""Direct company-library linking for deal narrative generation.

Company documents remain in their existing Mistral Library. This service stores
only their references and never downloads or uploads duplicate document bytes.
"""

import logging
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models.deal import Deal
from app.models.library_sync_log import LibrarySyncLog
from app.services.deal_service import DealService
from app.services.mcp_service import MCPClientService
from app.services.mistral_library_service import MistralLibraryService


logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _library_id_from_url(url: str | None) -> str | None:
    if not url or not url.startswith("mistral://"):
        return None
    reference = url.removeprefix("mistral://").strip("/")
    library_id, _, _document_id = reference.partition("/")
    return library_id or None


class LibrarySyncService:
    @staticmethod
    async def sync_mcp_documents(deal_id: str) -> None:
        """Refresh direct MCP/Mistral references without copying documents."""
        db = SessionLocal()
        try:
            deal = DealService.get_deal(db, deal_id)
            if not deal:
                logger.error("Company-library link failed: deal %s not found", deal_id)
                return
            if deal.library_sync_status == "syncing":
                logger.info("Company-library refresh already running for %s", deal_id)
                return

            deal.library_sync_status = "syncing"
            db.commit()

            details = await MCPClientService.get_company_details(deal.customer)
            documents = await MCPClientService.get_documents(deal.customer)
            company_library_id = details.get("mistral_library_id")
            if not company_library_id:
                company_library_id = next(
                    (
                        _library_id_from_url(
                            document.get("document_url") or document.get("url")
                        )
                        for document in documents
                        if _library_id_from_url(
                            document.get("document_url") or document.get("url")
                        )
                    ),
                    None,
                )

            if not company_library_id:
                deal.company_mistral_library_id = None
                deal.company_document_count = 0
                deal.library_sync_status = "ready"
                db.commit()
                logger.info("No company Mistral Library found for %s", deal.customer)
                return

            deal.company_mistral_library_id = company_library_id
            deal.company_document_count = len(documents)

            latest_logs = {
                log.doc_title: log
                for log in sorted(deal.sync_logs, key=lambda item: item.created_at)
            }
            seen_titles: set[str] = set()
            for document in documents:
                title = (
                    document.get("document_name")
                    or document.get("filename")
                    or document.get("name")
                    or "document.pdf"
                )
                url = document.get("document_url") or document.get("url")
                seen_titles.add(title)
                log = latest_logs.get(title)
                if not log:
                    log = LibrarySyncLog(
                        deal_id=deal.id,
                        doc_title=title,
                        created_at=_now(),
                    )
                    db.add(log)
                log.doc_url = url
                log.status = "linked"
                log.error = None
                log.started_at = None
                log.completed_at = _now()

            # Keep historical rows, but mark references no longer returned by MCP.
            for title, log in latest_logs.items():
                if log.status == "linked" and title not in seen_titles:
                    log.status = "removed"
                    log.completed_at = _now()

            deal.library_sync_status = "ready"
            db.commit()

            await MistralLibraryService.remove_legacy_mcp_copies(db, deal)
            await MistralLibraryService.sync_agents_to_libraries(
                db,
                MistralLibraryService.library_ids_for_deal(deal),
            )
            logger.info(
                "Linked %s company documents from Mistral Library %s to deal %s",
                len(documents),
                company_library_id,
                deal.id,
            )
        except Exception as exc:
            logger.error("Company-library link error for %s: %s", deal_id, exc)
            try:
                deal = db.query(Deal).filter(Deal.id == deal_id).first()
                if deal:
                    deal.library_sync_status = "error"
                    db.commit()
            except Exception:
                db.rollback()
        finally:
            db.close()

    @staticmethod
    async def check_for_new_documents(deal_id: str) -> dict:
        """Refresh direct links and return the current company-document count."""
        await LibrarySyncService.sync_mcp_documents(deal_id)
        db = SessionLocal()
        try:
            deal = db.query(Deal).filter(Deal.id == deal_id).first()
            total = deal.company_document_count if deal else 0
            return {
                "new_count": 0,
                "total_mcp": total,
                "already_synced": total,
                "mode": "direct_library_reference",
            }
        finally:
            db.close()
