from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.services.ephemeral_store import close_redis_client


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    close_redis_client()


app = FastAPI(
    title="YouTube Clone API",
    description="Backend API for a YouTube-inspired video hosting platform.",
    version="0.2.0",
    lifespan=lifespan,
)
app.include_router(api_router)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
