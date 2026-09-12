"""
races.py
--------
GET /races route — lists every race weekend that actually has ingested data
(joins the schedule JSON's round/location metadata with the distinct
Race/Year pairs present in pitwall.db), so the frontend's race selector
never drifts from what the backend can actually answer questions about.
"""

import json
import pathlib

from fastapi import APIRouter

from api.models import RaceInfo, RacesResponse
from utils.snowflake_client import get_connection

router = APIRouter()

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent.parent


@router.get("/races", response_model=RacesResponse, summary="List races with ingested data")
def get_races() -> RacesResponse:
    """
    Return every (round, country, year, location) race weekend for which
    lap data has actually been ingested into pitwall.db.

    Source of truth is the "laps" table's distinct Race/Year pairs — the
    schedule JSON files are only used to attach round number and city name
    for display. A race only appears here once its data exists, so races
    that haven't happened yet (or failed ingestion) are never listed.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT Race, Year FROM laps")
        available = set(cursor.fetchall())
        conn.close()
    except Exception:
        available = set()

    races: list[RaceInfo] = []
    for year in sorted({y for _, y in available}):
        schedule_path = ROOT_DIR / "data" / f"schedule_{year}.json"
        if not schedule_path.exists():
            continue

        schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
        seen_countries: set[str] = set()

        for entry in schedule:
            country = entry["country"]
            if (country, year) not in available:
                continue
            # A handful of seasons run two races in the same country (e.g.
            # Emilia Romagna + Italy both tagged "Italy") but ingestion keys
            # only on country name, so there's one ingested dataset per
            # country per year — skip duplicates rather than list a round
            # whose data isn't actually distinguishable from the first.
            if country in seen_countries:
                continue
            seen_countries.add(country)

            races.append(
                RaceInfo(
                    round=entry["round"],
                    country=country,
                    year=year,
                    location=entry["location"],
                )
            )

    races.sort(key=lambda r: (r.year, r.round))
    return RacesResponse(races=races)
