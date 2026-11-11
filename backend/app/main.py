from fastapi import FastAPI

app = FastAPI(title="YouTube Clone API", description="Backend API for a YouTube-inspired video hosting platform.", version="0.1.0")


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
