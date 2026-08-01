"""Local MCP server backed by PostgreSQL and Mistral Document Library."""

from __future__ import annotations

import json
import logging

from mcp.server.fastmcp import FastMCP
from mistralai.client import Mistral

from catalog import PDF_FILES, TABLE_NAMES
from database import (
    delete_company,
    describe_table,
    fetch_table_rows,
    get_company,
    get_document,
    get_registered_client,
    init_db,
    list_companies as db_list_companies,
    list_documents,
    list_registered_clients as db_list_registered_clients,
    upsert_registered_client,
)
from manufacture import manufacture_company_data as manufacture
from settings import settings


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("local_mcp")

mcp = FastMCP(
    "Local Credit Intelligence MCP",
    instructions=(
        "Local-only credit intelligence server. Company documents are stored in "
        "Mistral Libraries and structured records are stored in PostgreSQL."
    ),
    host=settings.mcp_host,
    port=settings.mcp_port,
)


@mcp.tool()
def manufacture_company_data(
    company_name: str,
    industry: str,
    geography: str,
) -> dict:
    """Manufacture 17 PDFs and 16 PostgreSQL credit tables for one company."""
    return manufacture(company_name, industry, geography)


@mcp.tool()
def list_companies() -> str:
    """List manufactured and developer-registered real-world companies."""
    companies = []
    seen_names = set()
    for company in db_list_companies():
        seen_names.add(company["name"].strip().lower())
        companies.append(
            {
                **company,
                "blob_url": (
                    f"mistral://{company['mistral_library_id']}"
                    if company.get("mistral_library_id")
                    else ""
                ),
                "storage": "mistral_library",
                "data_source": "manufactured",
            }
        )
    for client in db_list_registered_clients():
        if client["legal_name"].strip().lower() in seen_names:
            continue
        documents = _list_registered_library_documents(client)
        companies.append(
            {
                "name": client["legal_name"],
                "industry": client["industry"],
                "geography": client["geography"],
                "segment": "Mid Corporate",
                "kyc_status": "Pending",
                "mistral_library_id": client["mistral_library_id"],
                "document_count": len(documents),
                "library_access_error": client.get("_library_access_error"),
                "blob_url": f"mistral://{client['mistral_library_id']}",
                "storage": "mistral_library",
                "data_source": "real_world",
            }
        )
    companies.sort(key=lambda item: item["name"].lower())
    return json.dumps({"companies": companies}, default=str, indent=2)


@mcp.tool()
def register_real_world_client(
    legal_name: str,
    industry: str,
    geography: str,
    library_id: str,
) -> dict:
    """Add or update a real-world client for the New Deal company dropdown."""
    client = upsert_registered_client(
        legal_name,
        industry,
        geography,
        library_id,
    )
    return {
        "legal_name": client["legal_name"],
        "industry": client["industry"],
        "geography": client["geography"],
        "library_id": client["mistral_library_id"],
        "data_source": "real_world",
    }


@mcp.tool()
def list_registered_real_world_clients() -> str:
    """List clients manually registered by a developer in PostgreSQL."""
    return json.dumps(
        {"clients": db_list_registered_clients()},
        default=str,
        indent=2,
    )


def _list_registered_library_documents(client: dict) -> list[dict]:
    """Read documents directly from a registered Mistral Library."""
    if not settings.mistral_api_key:
        logger.warning("MISTRAL_API_KEY is not configured; cannot list library files")
        return []
    try:
        response = Mistral(
            api_key=settings.mistral_api_key
        ).beta.libraries.documents.list(
            library_id=client["mistral_library_id"],
            page_size=100,
        )
    except Exception as exc:
        logger.warning(
            "Could not list Mistral documents for %s: %s",
            client["legal_name"],
            exc,
        )
        client["_library_access_error"] = str(exc)
        return []
    documents = []
    for document in response.data:
        data = (
            document.model_dump()
            if hasattr(document, "model_dump")
            else vars(document)
        )
        documents.append(
            {
                "document_name": data.get("name") or f"{data['id']}.pdf",
                "document_url": (
                    f"mistral://{client['mistral_library_id']}/{data['id']}"
                ),
                "summary": data.get("summary") or "Real-world source document.",
                "status": data.get("processing_status") or str(
                    data.get("process_status", "uploaded")
                ),
                "storage": "mistral_library",
            }
        )
    return documents


@mcp.tool()
def retrieve_company_details(company_name: str) -> str:
    """Retrieve borrower details stored in local PostgreSQL."""
    company = get_company(company_name)
    if not company:
        client = get_registered_client(company_name)
        if client:
            return json.dumps(
                {
                    "name": client["legal_name"],
                    "industry": client["industry"],
                    "geography": client["geography"],
                    "segment": "Mid Corporate",
                    "kyc_status": "Pending",
                    "mistral_library_id": client["mistral_library_id"],
                    "data_source": "real_world",
                },
                default=str,
                indent=2,
            )
        return f"No details found for company '{company_name}'."
    return json.dumps(
        {
            "name": company["name"],
            "industry": company["industry"],
            "geography": company["geography"],
            "segment": company["segment"],
            "kyc_status": company["kyc_status"],
            "mistral_library_id": company["mistral_library_id"],
        },
        default=str,
        indent=2,
    )


@mcp.tool()
def retrieve_company_documents(company_name: str) -> str:
    """List the company's 17 Mistral Library documents and summaries."""
    documents = []
    for doc in list_documents(company_name):
        documents.append(
            {
                "document_name": doc["document_name"],
                "document_url": (
                    f"mistral://{doc['mistral_library_id']}/"
                    f"{doc['mistral_document_id']}"
                    if doc["mistral_document_id"]
                    else doc["local_path"]
                ),
                "summary": doc["summary"],
                "status": doc["processing_status"],
                "storage": (
                    "mistral_library"
                    if doc["mistral_document_id"]
                    else "local_staging"
                ),
            }
        )
    if not documents:
        client = get_registered_client(company_name)
        if client:
            documents = _list_registered_library_documents(client)
    if not documents:
        return f"No documents found for company '{company_name}'."
    return json.dumps(
        {"company": company_name, "documents": documents},
        default=str,
        indent=2,
    )


@mcp.tool()
def retrieve_company_document_summaries(company_name: str) -> str:
    """Return document summaries used by Credit Dossier orchestration."""
    documents = list_documents(company_name)
    if not documents:
        client = get_registered_client(company_name)
        if client:
            registered_documents = _list_registered_library_documents(client)
            return json.dumps(
                [
                    {
                        "document_name": doc["document_name"],
                        "summary": doc["summary"],
                    }
                    for doc in registered_documents
                ],
                indent=2,
            )
        return f"No document summaries found for company '{company_name}'."
    return json.dumps(
        [
            {
                "document_name": doc["document_name"],
                "summary": doc["summary"],
            }
            for doc in documents
        ],
        indent=2,
    )


@mcp.tool()
def check_company_processing_status(company_name: str) -> str:
    """Report local/Mistral storage status for all company PDFs."""
    documents = list_documents(company_name)
    uploaded = sum(1 for doc in documents if doc["mistral_document_id"])
    return json.dumps(
        {
            "company": company_name,
            "total_documents": len(documents),
            "uploaded_to_mistral": uploaded,
            "local_only": len(documents) - uploaded,
            "is_finished": len(documents) == len(PDF_FILES),
        },
        indent=2,
    )


@mcp.tool()
def remove_company(company_name: str) -> str:
    """Delete local PostgreSQL records for a company (not its Mistral Library)."""
    if delete_company(company_name):
        return f"Deleted local MCP data for '{company_name}'."
    return f"Company '{company_name}' not found."


@mcp.tool()
def get_mistral_library_id(company_name: str) -> str:
    """Return the Mistral Library ID for one company."""
    company = get_company(company_name)
    if company:
        return str(company.get("mistral_library_id") or "")
    client = get_registered_client(company_name)
    return str(client.get("mistral_library_id") or "") if client else ""


@mcp.tool()
def list_credit_tables(company_name: str) -> list[str]:
    """List the 16 PostgreSQL credit tables available for a company."""
    if not get_company(company_name):
        raise ValueError(f'Company "{company_name}" is not configured.')
    return list(TABLE_NAMES)


@mcp.tool()
def describe_credit_table(company_name: str, table_name: str) -> dict:
    """Describe a credit table and return its company-scoped row count."""
    return describe_table(company_name, table_name)


@mcp.tool()
def fetch_credit_table_rows(
    company_name: str,
    table_name: str,
    limit: int = 20,
) -> list[dict]:
    """Fetch up to 100 manufactured rows from an allowed credit table."""
    return fetch_table_rows(company_name, table_name, limit)


@mcp.tool()
def retrieve_company_structured_data(
    company_name: str,
    table_names_csv: str = "",
    rows_per_table: int = 20,
) -> str:
    """Return company-scoped PostgreSQL rows for several credit tables at once."""
    if not get_company(company_name):
        raise ValueError(f'Company "{company_name}" is not configured.')
    requested = (
        [name.strip() for name in table_names_csv.split(",") if name.strip()]
        if table_names_csv
        else list(TABLE_NAMES)
    )
    unknown = sorted(set(requested) - set(TABLE_NAMES))
    if unknown:
        raise ValueError(f"Unknown credit tables: {', '.join(unknown)}")
    safe_limit = max(1, min(rows_per_table, 100))
    tables = {
        table_name: rows
        for table_name in requested
        if (rows := fetch_table_rows(company_name, table_name, safe_limit))
    }
    return json.dumps(
        {
            "company": company_name,
            "table_count": len(tables),
            "row_count": sum(len(rows) for rows in tables.values()),
            "tables": tables,
        },
        default=str,
    )


@mcp.tool()
def list_mistral_pdf_tools(company_name: str) -> list[dict]:
    """List the 17 PDF retrieval tools and their Mistral document IDs."""
    company = get_company(company_name)
    if not company:
        raise ValueError(f'Company "{company_name}" is not configured.')
    documents = {
        doc["document_name"]: doc for doc in list_documents(company_name)
    }
    return [
        {
            "number": number,
            "name": filename,
            "toolName": f"get_{filename.removesuffix('.pdf').lower()}_content",
            "documentId": documents.get(filename, {}).get("mistral_document_id"),
            "libraryId": company.get("mistral_library_id"),
        }
        for number, filename in enumerate(PDF_FILES, start=1)
    ]


def fetch_pdf_text(
    company_name: str,
    filename: str,
    page_start: int | None = None,
    page_end: int | None = None,
) -> dict:
    company = get_company(company_name)
    document = get_document(company_name, filename)
    if not company or not document:
        raise ValueError(
            f'PDF "{filename}" is not configured for company "{company_name}".'
        )
    library_id = company.get("mistral_library_id")
    document_id = document.get("mistral_document_id")
    if not library_id or not document_id:
        raise ValueError(
            "The PDF exists locally but has not been uploaded to Mistral Library."
        )
    if not settings.mistral_api_key:
        raise ValueError("MISTRAL_API_KEY is not configured.")
    kwargs: dict[str, object] = {
        "library_id": library_id,
        "document_id": document_id,
    }
    if page_start is not None:
        kwargs["page_start"] = page_start
    if page_end is not None:
        kwargs["page_end"] = page_end
    response = Mistral(
        api_key=settings.mistral_api_key
    ).beta.libraries.documents.text_content(**kwargs)
    data = response.model_dump() if hasattr(response, "model_dump") else vars(response)
    return {
        "name": filename,
        "documentId": document_id,
        "libraryId": library_id,
        "pageStart": page_start,
        "pageEnd": page_end,
        "text": data.get("text", ""),
    }


def register_pdf_tool(filename: str) -> None:
    tool_name = f"get_{filename.removesuffix('.pdf').lower()}_content"

    @mcp.tool(
        name=tool_name,
        description=f"Return Mistral-extracted text from {filename}.",
    )
    def pdf_content(
        company_name: str,
        page_start: int | None = None,
        page_end: int | None = None,
    ) -> dict:
        return fetch_pdf_text(company_name, filename, page_start, page_end)


for pdf_filename in PDF_FILES:
    register_pdf_tool(pdf_filename)


def main() -> None:
    logger.info("Initialising local PostgreSQL MCP database")
    init_db()
    logger.info(
        "Starting local MCP on %s:%s using %s",
        settings.mcp_host,
        settings.mcp_port,
        settings.mcp_transport,
    )
    mcp.run(transport=settings.mcp_transport)


if __name__ == "__main__":
    main()
