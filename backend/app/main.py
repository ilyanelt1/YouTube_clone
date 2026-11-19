from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.router import api_router
from app.db.session import get_db
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
    """Liveness probe: the API process is running."""
    return {"status": "ok"}


@app.get("/ready", tags=["health"])
def readiness_check(db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    """Readiness probe: the API can successfully reach PostgreSQL."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc

    return {"status": "ready", "database": "ok"}
