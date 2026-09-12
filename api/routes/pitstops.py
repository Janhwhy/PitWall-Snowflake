"""
pitstops.py
-----------
GET /pit-stops route — the full per-race pit stop log (every stop, every
driver), computed directly via SQL against pitwall.db: no LLM involved.

Pit-lane duration = next lap's PitOutTime minus this lap's PitInTime, same
approach as the fastest-pitstop calculation in race_stats.py.
"""

import pandas as pd
from fastapi import APIRouter

from api.models import PitStopLogEntry, PitStopLogResponse
from api.race_utils import parse_race_label
from utils.snowflake_client import get_connection

router = APIRouter()


def _seconds(raw) -> float | None:
    """Parse a FastF1 Timedelta string (e.g. '0 days 01:33:29.565000') to seconds."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    try:
        return pd.to_timedelta(raw).total_seconds()
    except Exception:
        return None


@router.get("/pit-stops", response_model=PitStopLogResponse, summary="Full per-race pit stop log")
def get_pit_stops(race: str = "Monaco 2025") -> PitStopLogResponse:
    """Return every pit stop for a race, ordered by lap number."""
    race_name, year = parse_race_label(race)
    response = PitStopLogResponse(race=race_name or race, year=year or 0)

    if not race_name or not year:
        return response

    conn = get_connection()
    cursor = conn.cursor()
    params = (race_name, year)

    cursor.execute(
        """
        SELECT p.Driver, d.FullName, d.Team, p.LapNumber, p.Compound, p.TyreLife, p.PitInTime, l2.PitOutTime
        FROM pitstops p
        JOIN drivers d ON d.Driver = p.Driver AND d.Race = p.Race AND d.Year = p.Year
        LEFT JOIN laps l2 ON l2.Driver = p.Driver AND l2.Race = p.Race AND l2.Year = p.Year
                          AND l2.LapNumber = p.LapNumber + 1
        WHERE p.Race = %s AND p.Year = %s
        ORDER BY p.LapNumber ASC
        """,
        params,
    )
    rows = cursor.fetchall()
    conn.close()

    entries: list[PitStopLogEntry] = []
    for drv, name, team, lap_no, compound, tyre_life, pit_in, pit_out in rows:
        t_in, t_out = _seconds(pit_in), _seconds(pit_out)
        duration = round(t_out - t_in, 3) if (t_in is not None and t_out is not None and t_out > t_in) else None
        entries.append(
            PitStopLogEntry(
                driver=drv, full_name=name, team=team, lap_number=int(lap_no),
                compound=compound, tyre_life=tyre_life, duration_seconds=duration,
            )
        )

    response.pit_stops = entries
    return response
