
from typing import Annotated
from fastapi import Path as InputPath
from fastapi import APIRouter, Depends, HTTPException, Response
from typing import List, Dict, Any

from app.services.mcp_service import MCPClientService
from app.auth import get_current_user
from app.models.user import User
from app.responses import Utf8JSONResponse

router = APIRouter(prefix="/api/companies", tags=["companies"], default_response_class=Utf8JSONResponse)

@router.get("", response_model=List[Dict[str, Any]])
async def list_companies(response: Response, current_user: User = Depends(get_current_user)):
    """List all companies from MCP."""
    response.headers["Cache-Control"] = "no-store"
    # if not MCPClientService.is_connected:
    #     raise HTTPException(status_code=503, detail="MCP server is currently unreachable.")
    if not MCPClientService.is_connected:
        connected = await MCPClientService.connect()
        if not connected:
            raise HTTPException(
                status_code=503,
                detail="MCP server is currently unreachable.",
            )
    companies = await MCPClientService.list_companies(current_user.user_id)
    return companies

@router.get("/{company_name}/documents", response_model=List[Dict[str, Any]])
async def get_company_documents(company_name: Annotated[str, InputPath(min_length=1, max_length=256)], current_user: User = Depends(get_current_user)):
    """Get all documents for a specific company from MCP."""
    # if not MCPClientService.is_connected:
    #     raise HTTPException(status_code=503, detail="MCP server is currently unreachable.")
    if not MCPClientService.is_connected:
        connected = await MCPClientService.connect()
        if not connected:
            raise HTTPException(
                status_code=503,
                detail="MCP server is currently unreachable.",
            )    
    docs = await MCPClientService.get_documents(company_name, current_user.user_id)
    return docs

@router.get("/{company_name}/details", response_model=Dict[str, Any])
async def get_company_details(company_name: Annotated[str, InputPath(min_length=1, max_length=256)], response: Response, current_user: User = Depends(get_current_user)):
    """Get details for a specific company from MCP."""
    response.headers["Cache-Control"] = "no-store"
    # if not MCPClientService.is_connected:
    #     raise HTTPException(status_code=503, detail="MCP server is currently unreachable.")
    if not MCPClientService.is_connected:
        connected = await MCPClientService.connect()
        if not connected:
            raise HTTPException(
                status_code=503,
                detail="MCP server is currently unreachable.",
            )
    details = await MCPClientService.get_company_details(company_name, current_user.user_id)
    return details
