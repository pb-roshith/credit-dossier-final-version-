"""
Pydantic schemas for Deal, Section, AuditEntry, and Version.
"""

import json
from datetime import datetime
from typing import Optional
from urllib.parse import urlsplit
from pydantic import BaseModel, Field, field_validator


# ── Upload (nested — legacy) ───────────────────────────────────
class UploadBrief(BaseModel):
    id: str
    source_type: str
    filename: Optional[str] = None
    url: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Deal Document (new deal-level docs) ────────────────────────
class DealDocumentResponse(BaseModel):
    id: str
    source_type: str
    filename: Optional[str] = None
    url: Optional[str] = None
    note: Optional[str] = None
    extraction_method: Optional[str] = None
    page_count: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SectionDocumentLinkResponse(BaseModel):
    id: str
    document: DealDocumentResponse
    created_at: datetime

    model_config = {"from_attributes": True}


class LinkDocumentsRequest(BaseModel):
    document_ids: list[str]


# ── Library File (Mistral Library) ─────────────────────────────
class LibraryFileResponse(BaseModel):
    id: str
    mistral_file_id: str
    filename: str
    source_type: str
    file_size: Optional[int] = None
    note: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Library Sync Log ───────────────────────────────────────────
class LibrarySyncLogResponse(BaseModel):
    id: str
    doc_title: str
    doc_url: Optional[str] = None
    status: str
    error: Optional[str] = None
    file_size: Optional[int] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Section ─────────────────────────────────────────────────────
class SectionResponse(BaseModel):
    id: str
    section_key: str
    title: str
    description: str
    sources: str
    expected_output: str
    optional: bool
    state: str
    order_index: int
    generated_content: Optional[str] = None
    original_generated_content: Optional[str] = None
    final_generated_content: Optional[str] = None
    custom_instructions: Optional[str] = None
    accuracy_score: Optional[float] = None
    accuracy_details: Optional[dict] = None
    output_template: Optional[str] = None
    template_file_path: Optional[str] = None
    orchestration_strategy: Optional[str] = None
    moderation_status: Optional[str] = None
    moderation_details: Optional[dict] = None
    observability_details: Optional[dict] = None
    source_urls: list[str] = []
    url_scrape_details: Optional[list[dict]] = None
    uploads: list[UploadBrief] = []  # Legacy
    document_links: list[SectionDocumentLinkResponse] = []  # New

    model_config = {"from_attributes": True}

    @field_validator("accuracy_details", "moderation_details", "observability_details", mode="before")
    @classmethod
    def parse_json_details(cls, v):
        """Parse JSON string fields (DB storage) to dict."""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return None
        return v

    @field_validator("source_urls", "url_scrape_details", mode="before")
    @classmethod
    def parse_json_lists(cls, v):
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError):
                return []
        return v or []


class SectionUpdate(BaseModel):
    sources: Optional[str] = None
    expected_output: Optional[str] = None
    custom_instructions: Optional[str] = None
    output_template: Optional[str] = None
    generated_content: Optional[str] = None
    state: Optional[str] = None
    source_urls: Optional[list[str]] = None

    @field_validator("source_urls")
    @classmethod
    def validate_source_urls(cls, value):
        if value is None:
            return value
        if len(value) > 10:
            raise ValueError("A section can contain at most 10 URLs.")
        normalized: list[str] = []
        for raw_url in value:
            url = raw_url.strip()
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError(f"Invalid HTTP/HTTPS URL: {raw_url}")
            if len(url) > 2048:
                raise ValueError("A URL cannot exceed 2048 characters.")
            if url not in normalized:
                normalized.append(url)
        return normalized


# ── Audit Entry ─────────────────────────────────────────────────
class AuditEntryResponse(BaseModel):
    id: str
    action: str
    subject: str
    user: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Version ─────────────────────────────────────────────────────
class VersionCreate(BaseModel):
    notes: str = ""


class VersionReviewRequest(BaseModel):
    comments: str = Field(default="", max_length=4000)


class VersionResponse(BaseModel):
    id: str
    notes: str
    status: str
    review_comments: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class NarrativeVersionResponse(BaseModel):
    id: str
    deal_id: str
    section_id: str
    content: str
    version_type: str
    parent_version_id: Optional[str] = None
    created_by: str
    is_final: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Deal ────────────────────────────────────────────────────────
class DealCreate(BaseModel):
    customer: str = Field(..., min_length=1, max_length=256)
    customer_type: str = "Existing"
    industry: str = ""
    segment: str = "Mid Corporate"
    geography: str = ""
    kyc: str = "pending"
    facility: str = "Term Loan"
    currency: str = "INR"
    amount: float = 0
    tenure: int = 60
    pricing: str = ""
    repayment: str = ""
    collateral: bool = False
    due: str = ""


class DealUpdate(BaseModel):
    customer: Optional[str] = None
    customer_type: Optional[str] = None
    industry: Optional[str] = None
    segment: Optional[str] = None
    geography: Optional[str] = None
    kyc: Optional[str] = None
    facility: Optional[str] = None
    currency: Optional[str] = None
    amount: Optional[float] = None
    tenure: Optional[int] = None
    pricing: Optional[str] = None
    repayment: Optional[str] = None
    collateral: Optional[bool] = None
    due: Optional[str] = None
    status: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    theme_palette: Optional[str] = None


class DealResponse(BaseModel):
    id: str
    customer: str
    customer_type: str
    industry: str
    segment: str
    geography: str
    city: str
    sector: str
    kyc: str
    facility: str
    currency: str
    amount: float
    tenure: int
    pricing: str
    repayment: str
    collateral: bool
    due: str
    owner: str
    status: str
    created_at: datetime
    updated_at: datetime
    mistral_library_id: Optional[str] = None
    company_mistral_library_id: Optional[str] = None
    company_document_count: int = 0
    library_sync_status: str
    primary_color: str
    secondary_color: str
    theme_palette: list[str] = []

    sections: list[SectionResponse] = []
    documents: list[DealDocumentResponse] = []  # Deal-level documents (legacy)
    library_files: list[LibraryFileResponse] = []  # Mistral Library files
    sync_logs: list[LibrarySyncLogResponse] = []
    audit_entries: list[AuditEntryResponse] = []
    versions: list[VersionResponse] = []

    model_config = {"from_attributes": True}

    @field_validator("theme_palette", mode="before")
    @classmethod
    def parse_theme_palette(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return ["#002060", "#800020"]
        return v or ["#002060", "#800020"]


class DealListResponse(BaseModel):
    """Lighter response for the pipeline table — excludes full section content."""
    id: str
    customer: str
    customer_type: str
    industry: str
    segment: str
    geography: str
    city: str
    sector: str
    kyc: str
    facility: str
    currency: str
    amount: float
    tenure: int
    pricing: str
    repayment: str
    collateral: bool
    due: str
    owner: str
    status: str
    library_sync_status: str = "not_started"
    created_at: datetime
    updated_at: datetime
    sections_ready: int = 0
    sections_total: int = 0
    versions_count: int = 0

    model_config = {"from_attributes": True}
