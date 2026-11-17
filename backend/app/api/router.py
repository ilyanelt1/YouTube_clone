from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.library import router as library_router
from app.api.routes.social import router as social_router
from app.api.routes.videos import router as videos_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(videos_router)
api_router.include_router(social_router)
api_router.include_router(library_router)
