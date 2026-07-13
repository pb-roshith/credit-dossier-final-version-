import logging
import httpx
import asyncio
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.deal import Deal
from app.models.library_sync_log import LibrarySyncLog
from app.services.deal_service import DealService
from app.services.mcp_service import MCPClientService
from app.services.mistral_library_service import MistralLibraryService

logger = logging.getLogger(__name__)

def _now() -> datetime:
    return datetime.now(timezone.utc)

class LibrarySyncService:

    @staticmethod
    async def sync_mcp_documents(deal_id: str):
        """
        Background task to sync MCP documents for a deal into the Mistral Library.
        Tracks progress via LibrarySyncLog.
        """
        db = SessionLocal()
        try:
            deal = DealService.get_deal(db, deal_id)
            if not deal:
                logger.error(f"Sync failed: Deal {deal_id} not found")
                return

            deal.library_sync_status = "syncing"
            db.commit()

            logger.info(f"Starting MCP document sync for {deal.customer}")

            # 1. Fetch available docs from MCP
            docs = await MCPClientService.get_documents(deal.customer)
            if not docs:
                logger.info(f"No MCP docs found for {deal.customer}")
                deal.library_sync_status = "ready"
                db.commit()
                return

            # 2. Compare against existing library files and queued logs
            existing_filenames = {f.filename for f in deal.library_files}
            existing_logs = {log.doc_title for log in deal.sync_logs if log.status not in ["failed", "skipped"]}
            
            new_docs_to_sync = []
            for doc in docs:
                url = doc.get("document_url") or doc.get("url")
                filename = doc.get("document_name") or doc.get("filename") or doc.get("name") or "document.pdf"
                
                if not url:
                    continue
                if filename in existing_filenames or filename in existing_logs:
                    continue
                
                new_docs_to_sync.append({"url": url, "filename": filename})

            if not new_docs_to_sync:
                logger.info(f"No new docs to sync for {deal.customer}")
                # check if there are running syncs, otherwise ready
                running = [log for log in deal.sync_logs if log.status in ["queued", "downloading", "uploading"]]
                if not running:
                    deal.library_sync_status = "ready"
                db.commit()
                return

            # 3. Queue the new docs
            logs = []
            for doc in new_docs_to_sync:
                log = LibrarySyncLog(
                    deal_id=deal.id,
                    doc_title=doc["filename"],
                    doc_url=doc["url"],
                    status="queued"
                )
                db.add(log)
                logs.append(log)
            db.commit()

            # 4. Process downloads and uploads
            has_errors = False
            async with httpx.AsyncClient() as client:
                for log in logs:
                    try:
                        # Downloading
                        log.status = "downloading"
                        log.started_at = _now()
                        db.commit()
                        
                        resp = await client.get(log.doc_url, timeout=60.0)
                        resp.raise_for_status()
                        file_bytes = resp.content
                        log.file_size = len(file_bytes)

                        # Uploading
                        log.status = "uploading"
                        db.commit()

                        # Re-fetch deal to prevent detached instance issues during upload
                        deal = DealService.get_deal(db, deal_id)
                        
                        await MistralLibraryService.upload_file_to_library(
                            db=db,
                            deal=deal,
                            file_bytes=file_bytes,
                            filename=log.doc_title,
                            source_type="mcp_auto",
                            note="Auto-uploaded from MCP Server"
                        )

                        # Completed
                        log.status = "completed"
                        log.completed_at = _now()
                        db.commit()
                        
                        # Wait a bit between uploads to respect rate limits
                        await asyncio.sleep(1.5)

                    except Exception as e:
                        logger.error(f"Failed to sync {log.doc_url}: {e}")
                        log.status = "failed"
                        log.error = str(e)
                        log.completed_at = _now()
                        has_errors = True
                        db.commit()

            # 5. Finalize status
            deal = DealService.get_deal(db, deal_id)
            running_logs = [log for log in deal.sync_logs if log.status in ["queued", "downloading", "uploading"]]
            if not running_logs:
                deal.library_sync_status = "partial" if has_errors else "ready"
                db.commit()

        except Exception as e:
            logger.error(f"Library sync error for deal {deal_id}: {e}")
            try:
                deal = db.query(Deal).filter(Deal.id == deal_id).first()
                if deal:
                    deal.library_sync_status = "error"
                    db.commit()
            except:
                pass
        finally:
            db.close()

    @staticmethod
    async def check_for_new_documents(deal_id: str) -> dict:
        """
        Called when deal is opened to check if new documents exist on MCP.
        If yes, auto-triggers sync in the background (does not await the full sync).
        """
        db = SessionLocal()
        try:
            deal = DealService.get_deal(db, deal_id)
            if not deal:
                return {"new_count": 0, "total_mcp": 0, "already_synced": 0}
            
            docs = await MCPClientService.get_documents(deal.customer)
            if not docs:
                return {"new_count": 0, "total_mcp": 0, "already_synced": 0}
                
            existing_filenames = {f.filename for f in deal.library_files}
            existing_logs = {log.doc_title for log in deal.sync_logs if log.status not in ["failed", "skipped"]}
            
            new_count = 0
            for doc in docs:
                url = doc.get("document_url") or doc.get("url")
                filename = doc.get("document_name") or doc.get("filename") or doc.get("name") or "document.pdf"
                if url and filename not in existing_filenames and filename not in existing_logs:
                    new_count += 1

            if new_count > 0:
                # Since this is already running in a background task, we can just await it
                await LibrarySyncService.sync_mcp_documents(deal_id)

            return {
                "new_count": new_count,
                "total_mcp": len(docs),
                "already_synced": len(docs) - new_count
            }
        finally:
            db.close()
