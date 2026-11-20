"""
API v1 Master Router Aggregator.
"""

from fastapi import APIRouter

from src.api.v1.accounts import accounts_router, tasks_router
from src.api.v1.ai_copilot import router as ai_router
from src.api.v1.auth import router as auth_router
from src.api.v1.contacts import router as contacts_router
from src.api.v1.deals import router as deals_router
from src.api.v1.llm_credentials import router as llm_credentials_router
from src.api.v1.mcp import router as mcp_router

api_v1_router = APIRouter()
api_v1_router.include_router(auth_router)
api_v1_router.include_router(accounts_router)
api_v1_router.include_router(contacts_router)
api_v1_router.include_router(deals_router)
api_v1_router.include_router(tasks_router)
api_v1_router.include_router(ai_router)
api_v1_router.include_router(llm_credentials_router)
api_v1_router.include_router(mcp_router)
