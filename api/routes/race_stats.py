"""
race_stats.py
-------------
GET /race-stats route — computes deterministic post-race (and, where
Qualifying data exists, pre-race grid) facts directly via SQL against
pitwall.db: winner, podium, fastest lap, most-used tyre compound, pit stop
count, fastest pit lane time, laps led, and starting grid.

Unlike /ask, this never calls an LLM — these are exact facts, not open-ended
questions, so a direct query is both faster and can't hallucinate.
"""

import pandas as pd
from fastapi import APIRouter

from api.models import (
    CompoundUsage,
    DriverStanding,
    FastestLap,
    GridSlot,
    LapsLed,
    PitStopInfo,
    RaceStatsResponse,
)
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


@router.get("/race-stats", response_model=RaceStatsResponse, summary="Deterministic post-race / grid stats")
def get_race_stats(race: str = "Monaco 2025") -> RaceStatsResponse:
    """
    Compute race-summary stats directly from pitwall.db — no LLM involved.

    Parameters
    ----------
    race : str
        Race label like "Monaco 2025".

    Returns
    -------
    RaceStatsResponse
        Winner/podium/fastest-lap/tyre/pit-stop/grid facts. Fields default to
        empty/None if the underlying data isn't available for this race
        (e.g. `pole`/`grid` stay empty if Qualifying wasn't ingested for it).
    """
    race_name, year = parse_race_label(race)
    response = RaceStatsResponse(race=race_name or race, year=year or 0)

    if not race_name or not year:
        return response

    conn = get_connection()
    cursor = conn.cursor()
    params = (race_name, year)

    # ── Winner + podium (Position at the final lap, joined to real names) ──
    cursor.execute(
        """
        SELECT l.Driver, d.FullName, d.Team, l.Position
        FROM laps l
        JOIN drivers d ON d.Driver = l.Driver AND d.Race = l.Race AND d.Year = l.Year
        WHERE l.Race = %s AND l.Year = %s
          AND l.LapNumber = (SELECT MAX(LapNumber) FROM laps WHERE Race = %s AND Year = %s)
          AND l.Position IS NOT NULL AND l.Position <= 3
        ORDER BY l.Position ASC
        """,
        (*params, *params),
    )
    podium_rows = cursor.fetchall()
    response.podium = [
        DriverStanding(position=int(pos), driver=drv, full_name=name, team=team)
        for drv, name, team, pos in podium_rows
    ]
    if response.podium and response.podium[0].position == 1:
        response.winner = response.podium[0]

    # ── Fastest lap ──────────────────────────────────────────────────────────
    cursor.execute(
        """
        SELECT l.Driver, d.FullName, d.Team, l.LapNumber, l.LapTimeSeconds
        FROM laps l
        JOIN drivers d ON d.Driver = l.Driver AND d.Race = l.Race AND d.Year = l.Year
        WHERE l.Race = %s AND l.Year = %s AND l.LapTimeSeconds IS NOT NULL
        ORDER BY l.LapTimeSeconds ASC
        LIMIT 1
        """,
        params,
    )
    row = cursor.fetchone()
    if row:
        drv, name, team, lap_no, lap_time = row
        response.fastest_lap = FastestLap(
            driver=drv, full_name=name, team=team,
            lap_number=int(lap_no), lap_time_seconds=round(lap_time, 3),
        )

    # ── Average lap time (excludes in/out laps via a loose upper bound, so
    # pit-lane and safety-car laps don't skew it too far from a "racing" pace) ──
    cursor.execute(
        "SELECT AVG(LapTimeSeconds) FROM laps WHERE Race = %s AND Year = %s AND LapTimeSeconds IS NOT NULL",
        params,
    )
    avg_row = cursor.fetchone()
    if avg_row and avg_row[0] is not None:
        response.avg_lap_seconds = round(avg_row[0], 3)

    # ── Tyre compound breakdown ──────────────────────────────────────────────
    cursor.execute(
        """
        SELECT Compound, COUNT(*) AS c FROM laps
        WHERE Race = %s AND Year = %s AND Compound IS NOT NULL
        GROUP BY Compound ORDER BY c DESC
        """,
        params,
    )
    response.compound_breakdown = [CompoundUsage(compound=c, count=n) for c, n in cursor.fetchall()]
    if response.compound_breakdown:
        response.most_used_compound = response.compound_breakdown[0]

    # ── Pit stops: count + fastest (pit-lane time = next lap's PitOutTime
    # minus this lap's PitInTime; FastF1 records them on different laps) ────
    cursor.execute("SELECT COUNT(*) FROM pitstops WHERE Race = %s AND Year = %s", params)
    response.total_pitstops = cursor.fetchone()[0] or 0

    cursor.execute(
        """
        SELECT p.Driver, d.FullName, d.Team, p.LapNumber, p.PitInTime, l2.PitOutTime
        FROM pitstops p
        JOIN drivers d ON d.Driver = p.Driver AND d.Race = p.Race AND d.Year = p.Year
        JOIN laps l2 ON l2.Driver = p.Driver AND l2.Race = p.Race AND l2.Year = p.Year
                     AND l2.LapNumber = p.LapNumber + 1
        WHERE p.Race = %s AND p.Year = %s AND l2.PitOutTime IS NOT NULL
        """,
        params,
    )
    fastest_pit = None
    for drv, name, team, lap_no, pit_in, pit_out in cursor.fetchall():
        t_in, t_out = _seconds(pit_in), _seconds(pit_out)
        if t_in is None or t_out is None:
            continue
        duration = t_out - t_in
        if duration <= 0:
            continue  # guard against any mismatched lap pairing
        if fastest_pit is None or duration < fastest_pit.duration_seconds:
            fastest_pit = PitStopInfo(
                driver=drv, full_name=name, team=team,
                lap_number=int(lap_no), duration_seconds=round(duration, 3),
            )
    response.fastest_pitstop = fastest_pit

    # ── Laps led ──────────────────────────────────────────────────────────────
    cursor.execute(
        """
        SELECT l.Driver, d.FullName, COUNT(*) AS c
        FROM laps l
        JOIN drivers d ON d.Driver = l.Driver AND d.Race = l.Race AND d.Year = l.Year
        WHERE l.Race = %s AND l.Year = %s AND l.Position = 1
        GROUP BY l.Driver, d.FullName ORDER BY c DESC
        """,
        params,
    )
    response.laps_led = [LapsLed(driver=drv, full_name=name, laps_led=n) for drv, name, n in cursor.fetchall()]

    # ── Grid / pole (only present if Qualifying was ingested for this race) ──
    cursor.execute(
        """
        SELECT GridPosition, Driver, FullName, Team, Q1, Q2, Q3
        FROM qualifying WHERE Race = %s AND Year = %s
        ORDER BY GridPosition ASC
        """,
        params,
    )
    grid_rows = cursor.fetchall()
    if grid_rows:
        response.has_quali_data = True
        response.grid = [
            GridSlot(
                grid_position=int(pos), driver=drv, full_name=name, team=team,
                q1=q1, q2=q2, q3=q3,
            )
            for pos, drv, name, team, q1, q2, q3 in grid_rows
        ]
        response.pole = response.grid[0]

    conn.close()
    return response
