"""Read-only research API and landing page for AlphEdge."""
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.gzip import GZipMiddleware

from .explorer import router as explorer_router

api = FastAPI(title="AlphEdge Research", description="Historical research and model basket; no brokerage execution.")
api.add_middleware(GZipMiddleware, minimum_size=1024)
api.include_router(explorer_router)


@api.get("/api/health")
def health():
    return {"ok": True, "timestamp": datetime.now(timezone.utc).isoformat()}


@api.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/explore")
