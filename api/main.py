"""
main.py
-------
PitWall FastAPI application entry point.
Mounts all API routers, adds CORS middleware for the React frontend,
and logs ChromaDB chunk counts on startup.

Run with:
    uvicorn api.main:app --reload --port 8000
"""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import ask, brief, debrief, pitstops, races, race_stats, results, schedule, standings, status, weather

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="PitWall API",
    description=(
        "Multi-agent F1 race strategy assistant. "
        "Query specialist agents for tyre, weather, radio, rivals and circuit insights."
    ),
    version="1.0.0",
)

# ── CORS ────────────────────────────────────────────────────────────────────
# CORS_ORIGINS is a comma-separated allowlist (e.g. the Vercel frontend URL).
# Defaults to "*" so local dev keeps working with no env var set.
_cors_origins_env = os.getenv("CORS_ORIGINS", "*")
cors_origins = (
    ["*"] if _cors_origins_env.strip() == "*"
    else [origin.strip() for origin in _cors_origins_env.split(",") if origin.strip()]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ─────────────────────────────────────────────────────────────────
app.include_router(status.router, tags=["Health"])
app.include_router(ask.router, tags=["Strategy"])
app.include_router(brief.router, tags=["Strategy"])
app.include_router(debrief.router, tags=["Strategy"])
app.include_router(races.router, tags=["Strategy"])
app.include_router(race_stats.router, tags=["Strategy"])
app.include_router(results.router, tags=["Strategy"])
app.include_router(pitstops.router, tags=["Strategy"])
app.include_router(weather.router, tags=["Strategy"])
app.include_router(schedule.router, tags=["Schedule"])
app.include_router(standings.router, tags=["Standings"])


# ── Startup event ───────────────────────────────────────────────────────────
@app.on_event("startup")
async def log_collection_counts() -> None:
    """Log the number of chunks in each Snowflake RAG chunk table on startup."""
    from utils.snowflake_client import get_connection

    tables = {"laps": "laps_chunks", "weather": "weather_chunks",
              "radio": "radio_chunks", "pitstops": "pitstops_chunks"}

    conn = get_connection()
    try:
        cursor = conn.cursor()
        counts = {}
        for name, table in tables.items():
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            counts[name] = cursor.fetchone()[0]
    finally:
        conn.close()

    logger.info("=== PitWall Snowflake RAG Chunk Tables ===")
    for name, count in counts.items():
        logger.info("  %-10s : %d chunks", name, count)
    logger.info("====================================")


# ── Root ─────────────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"], summary="API liveness check")
def root() -> dict:
    """Simple liveness probe."""
    return {"status": "PitWall API is live"}
