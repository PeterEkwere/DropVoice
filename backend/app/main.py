from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.db.session import Base, engine
from app.routes.device import router as device_router
from app.routes.generations import router as generations_router
from app.routes.health import router as health_router
from app.routes.topups import router as topups_router
from app.routes.wallet import router as wallet_router
from app.services.queue import GenerationProcessor


GENERATION_JOB_ADDITIONS = [
    ("pace", "VARCHAR(16) DEFAULT 'normal'"),
    ("important_terms_raw", "TEXT"),
    ("compiled_transcript", "TEXT"),
]


async def ensure_generation_columns() -> None:
    async with engine.begin() as conn:
        existing = await conn.execute(text("PRAGMA table_info(generation_jobs)"))
        columns = {row[1] for row in existing.fetchall()}
        for column, ddl in GENERATION_JOB_ADDITIONS:
            if column not in columns:
                await conn.execute(text(f"ALTER TABLE generation_jobs ADD COLUMN {column} {ddl}"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    if engine.url.get_backend_name() == "sqlite":
        await ensure_generation_columns()

    processor = GenerationProcessor()
    app.state.generation_processor = processor
    task = asyncio.create_task(processor.run())
    try:
        yield
    finally:
        await processor.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(device_router, prefix=settings.api_prefix)
app.include_router(wallet_router, prefix=settings.api_prefix)
app.include_router(topups_router, prefix=settings.api_prefix)
app.include_router(generations_router, prefix=settings.api_prefix)
