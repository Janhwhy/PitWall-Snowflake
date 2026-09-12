"""
status.py
---------
GET /status route — reports the number of chunks backing each Snowflake
Cortex Search service.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from api.models import StatusResponse
from utils.snowflake_client import get_connection

router = APIRouter()

_CHUNK_TABLES = {"laps": "laps_chunks", "weather": "weather_chunks",
                 "radio": "radio_chunks", "pitstops": "pitstops_chunks"}


class F1DashStatusResponse(BaseModel):
    status: str


@router.get("/status", response_model=StatusResponse, summary="RAG chunk-table health check")
def get_status() -> StatusResponse:
    """
    Query every Snowflake RAG chunk table and return the current row counts.

    Returns
    -------
    StatusResponse
        A mapping of collection name → number of stored chunks.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        collections = {}
        for name, table in _CHUNK_TABLES.items():
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            collections[name] = cursor.fetchone()[0]
    finally:
        conn.close()
    return StatusResponse(collections=collections)


@router.get("/f1dash/status", response_model=F1DashStatusResponse, summary="f1-dash mock connection status check")
def get_f1dash_status() -> F1DashStatusResponse:
    """
    Return whether f1-dash is online or offline.
    Checks if a local service is listening on port 3001.
    """
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", 3001))
        s.close()
        return F1DashStatusResponse(status="online")
    except Exception:
        return F1DashStatusResponse(status="offline")
