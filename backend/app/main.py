from fastapi import FastAPI

from app.api.router import api_router

app = FastAPI(
    title="YouTube Clone API",
    description="Backend API for a YouTube-inspired video hosting platform.",
    version="0.2.0",
)
app.include_router(api_router)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
