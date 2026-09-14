from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from contextlib import asynccontextmanager

from app.api.routes import router, rt

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        rt.ingest()
    except FileNotFoundError:
        pass
    yield


app = FastAPI(title="SEALED", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="ui")
