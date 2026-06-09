from fastapi import APIRouter
from .auth import router as auth_router
from .sync import router as sync_router
from .holdings import router as holdings_router
from .files import router as files_router
from .chat import router as chat_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(sync_router)
api_router.include_router(holdings_router)
api_router.include_router(files_router)
api_router.include_router(chat_router)
