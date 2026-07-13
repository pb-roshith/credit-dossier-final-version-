from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any

from app.services.mcp_service import MCPClientService

router = APIRouter(prefix="/api/companies", tags=["companies"])

@router.get("", response_model=List[Dict[str, Any]])
async def list_companies():
    """List all companies from MCP."""
    if not MCPClientService.is_connected:
        raise HTTPException(status_code=503, detail="MCP server is currently unreachable.")
    companies = await MCPClientService.list_companies()
    return companies

@router.get("/{company_name}/documents", response_model=List[Dict[str, Any]])
async def get_company_documents(company_name: str):
    """Get all documents for a specific company from MCP."""
    if not MCPClientService.is_connected:
        raise HTTPException(status_code=503, detail="MCP server is currently unreachable.")
    docs = await MCPClientService.get_documents(company_name)
    return docs

@router.get("/{company_name}/details", response_model=Dict[str, Any])
async def get_company_details(company_name: str):
    """Get details for a specific company from MCP."""
    if not MCPClientService.is_connected:
        raise HTTPException(status_code=503, detail="MCP server is currently unreachable.")
    details = await MCPClientService.get_company_details(company_name)
    return details
