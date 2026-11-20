"""
MCP Tools Discovery & Execution Router for Authenticated Agents.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user, get_tenant_db, require_roles
from src.schemas.crm import AuthenticatedUser, MCPExecuteRequest, MCPToolResponse
from src.services.mcp_crm_server import CRM_MCP_TOOLS, MCPAgentExecutionEngine

router = APIRouter(prefix="/mcp", tags=["Model Context Protocol (MCP)"])


@router.get("/tools", response_model=list[MCPToolResponse], status_code=status.HTTP_200_OK)
async def list_mcp_tools(current_user: AuthenticatedUser = Depends(get_current_user)):
    return [MCPToolResponse(**t.model_dump()) for t in CRM_MCP_TOOLS]


@router.post("/execute", status_code=status.HTTP_200_OK)
async def execute_mcp_tool(
    payload: MCPExecuteRequest,
    current_user: AuthenticatedUser = Depends(require_roles(["admin", "sales_manager", "sales_rep"])),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await MCPAgentExecutionEngine.dispatch_tool(
        tool_name=payload.tool_name,
        arguments=payload.arguments,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        db=db,
    )
