"""
results.py
----------
GET /race-results route — full race classification (every driver, not just
the podium), computed directly via SQL against pitwall.db: no LLM involved.

Finishing order comes from the `drivers.FinishPosition` column (FastF1's own
classification, which already accounts for retirements that still completed
enough of the race to be classified). "Laps down" status is derived by
comparing each driver's completed lap count to the race leader's.
"""

from fastapi import APIRouter

from api.models import RaceResultRow, RaceResultsResponse
from api.race_utils import parse_race_label
from utils.snowflake_client import get_connection

router = APIRouter()


@router.get("/race-results", response_model=RaceResultsResponse, summary="Full race classification")
def get_race_results(race: str = "Monaco 2025") -> RaceResultsResponse:
    """
    Return every driver's finishing position, team, laps completed, and
    fastest-lap flag for a race, ordered by classification.
    """
    race_name, year = parse_race_label(race)
    response = RaceResultsResponse(race=race_name or race, year=year or 0)

    if not race_name or not year:
        return response

    conn = get_connection()
    cursor = conn.cursor()
    params = (race_name, year)

    cursor.execute(
        """
        SELECT d.Driver, d.FullName, d.Team, d.FinishPosition, COUNT(l.LapNumber) AS laps_completed
        FROM drivers d
        LEFT JOIN laps l ON l.Driver = d.Driver AND l.Race = d.Race AND l.Year = d.Year
        WHERE d.Race = %s AND d.Year = %s
        GROUP BY d.Driver, d.FullName, d.Team, d.FinishPosition
        ORDER BY d.FinishPosition ASC
        """,
        params,
    )
    rows = cursor.fetchall()

    cursor.execute(
        """
        SELECT Driver FROM laps
        WHERE Race = %s AND Year = %s AND LapTimeSeconds IS NOT NULL
        ORDER BY LapTimeSeconds ASC LIMIT 1
        """,
        params,
    )
    fastest_row = cursor.fetchone()
    fastest_driver = fastest_row[0] if fastest_row else None
    conn.close()

    if not rows:
        return response

    max_laps = max(r[4] for r in rows)

    results: list[RaceResultRow] = []
    for driver, full_name, team, finish_pos, laps_completed in rows:
        laps_down = max_laps - laps_completed
        if laps_down <= 0:
            status = "Finished"
        elif laps_down == 1:
            status = "+1 Lap"
        else:
            status = f"+{laps_down} Laps"

        results.append(
            RaceResultRow(
                position=int(finish_pos),
                driver=driver,
                full_name=full_name,
                team=team,
                laps_completed=int(laps_completed),
                status=status,
                is_fastest_lap=(driver == fastest_driver),
            )
        )

    response.results = results
    return response
