"""
export_tableau.py
------------------
Exports clean, pre-aggregated CSVs from data/pitwall.db for Tableau Public:
  exports/lap_level.csv
  exports/pitstop_level.csv
  exports/driver_race_summary.csv

See pitwall-tableau-handover.md for the full spec. Notable adaptations made
against the real schema (laps/pitstops/drivers/qualifying/weather, keyed by
Driver code + Race (=track/country name) + Year, not the drivers/races/
lap_times/pit_stops/results tables described in the handover):

- There is no race `date` column anywhere in pitwall.db. Dates are recovered
  by joining Race+Year against data/schedule_{year}.json (country -> date),
  which covers all 27 race/year combinations present in the DB.
- The `pitstops` table's PitOutTime is null for the vast majority of rows
  (it's only populated when the out-lap happens to land on the same row as
  the in-lap, which is rare). Real pit-in/pit-out pairs live in the `laps`
  table instead, one lap apart (PitInTime on the in-lap, PitOutTime on the
  following lap), so pit stop duration is computed from `laps`, not
  `pitstops`.
- `drivers` is already a one-row-per-driver-per-race table with
  FinishPosition, i.e. it plays the role of both `races`/`results` in the
  handover's schema. There's no separate DNF flag; FinishPosition is never
  null in this dataset (FastF1 gives a classified position even for
  retirements), but the join is still done as a left join and left null if
  a driver code from `laps` has no matching `drivers` row.
"""

import json
import pathlib

import pandas as pd

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "data" / "pitwall.db"
EXPORTS_DIR = ROOT_DIR / "exports"


def load_race_dates() -> dict:
    """(Race, Year) -> ISO 8601 date string, from data/schedule_{year}.json."""
    dates = {}
    for schedule_file in ROOT_DIR.glob("data/schedule_*.json"):
        year_str = schedule_file.stem.replace("schedule_", "")
        if not year_str.isdigit():
            continue
        year = int(year_str)
        with open(schedule_file, "r", encoding="utf-8") as f:
            for event in json.load(f):
                dates[(event["country"], year)] = event["date"]
    return dates


def build_driver_name_map(drivers: pd.DataFrame, qualifying: pd.DataFrame) -> dict:
    """Driver code -> single canonical FullName.

    Some codes have inconsistent FullName spellings across rows (e.g. 'ANT'
    appears as both 'Kimi Antonelli' and 'Andrea Kimi Antonelli'). Pick the
    most frequent name per code, breaking ties with the longest (most
    complete) spelling.
    """
    names = pd.concat(
        [drivers[["Driver", "FullName"]], qualifying[["Driver", "FullName"]]],
        ignore_index=True,
    ).dropna()

    counts = names.value_counts().reset_index(name="n")
    counts["name_len"] = counts["FullName"].str.len()
    counts = counts.sort_values(["Driver", "n", "name_len"], ascending=[True, False, False])
    return counts.drop_duplicates("Driver").set_index("Driver")["FullName"].to_dict()


def add_race_identity_columns(df: pd.DataFrame, race_dates: dict) -> pd.DataFrame:
    df = df.copy()
    df["race_id"] = df["Year"].astype(str) + "_" + df["Race"].str.replace(" ", "_")
    df["track"] = df["Race"]
    df["season"] = df["Year"]
    df["date"] = df.apply(lambda r: race_dates.get((r["Race"], r["Year"])), axis=1)
    return df


def pair_pit_stops(laps: pd.DataFrame) -> pd.DataFrame:
    """Pair each pit-in with the next pit-out (chronologically, per driver/race)
    to compute stop_number and duration from the `laps` table.
    """
    laps = laps.sort_values(["Driver", "Race", "Year", "LapNumber"])

    stops = []
    group_cols = ["Driver", "Team", "Race", "Year"]
    for (driver, team, race, year), g in laps.groupby(group_cols, sort=False):
        ins = g.loc[g["PitInTime"].notna(), ["LapNumber", "PitInTime"]].sort_values("PitInTime")
        outs = g.loc[g["PitOutTime"].notna(), ["LapNumber", "PitOutTime"]].sort_values("PitOutTime")

        j = 0
        stop_number = 0
        for _, in_row in ins.iterrows():
            in_time = in_row["PitInTime"]
            # skip any pit-out events that happened before/at this pit-in
            # (e.g. the formation-lap "out" at the start of the race)
            while j < len(outs) and outs.iloc[j]["PitOutTime"] <= in_time:
                j += 1
            stop_number += 1
            if j < len(outs):
                duration = (outs.iloc[j]["PitOutTime"] - in_time).total_seconds()
                j += 1
            else:
                duration = None
            stops.append(
                {
                    "Driver": driver,
                    "Team": team,
                    "Race": race,
                    "Year": year,
                    "stop_number": stop_number,
                    "duration": duration,
                }
            )

    stops_df = pd.DataFrame(stops)
    stops_df["total_stops_in_race"] = stops_df.groupby(["Driver", "Race", "Year"])[
        "stop_number"
    ].transform("count")
    return stops_df


def main():
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    import sqlite3

    conn = sqlite3.connect(DB_PATH)
    laps = pd.read_sql("SELECT * FROM laps", conn)
    drivers = pd.read_sql("SELECT * FROM drivers", conn)
    qualifying = pd.read_sql("SELECT * FROM qualifying", conn)
    conn.close()

    # --- cleaning -----------------------------------------------------
    for df in (laps, drivers, qualifying):
        df["Team"] = df["Team"].str.strip()
        df["Driver"] = df["Driver"].str.strip()

    laps["PitInTime"] = pd.to_timedelta(laps["PitInTime"], errors="coerce")
    laps["PitOutTime"] = pd.to_timedelta(laps["PitOutTime"], errors="coerce")

    race_dates = load_race_dates()
    driver_name_map = build_driver_name_map(drivers, qualifying)

    # =====================================================================
    # lap_level.csv
    # =====================================================================
    lap_level = add_race_identity_columns(laps, race_dates)
    lap_level["driver_id"] = lap_level["Driver"]
    lap_level["driver_name"] = lap_level["Driver"].map(driver_name_map)
    lap_level["team"] = lap_level["Team"]
    lap_level["lap_number"] = lap_level["LapNumber"].astype("Int64")
    lap_level["lap_time"] = lap_level["LapTimeSeconds"]

    fastest_per_race = lap_level.groupby("race_id")["lap_time"].transform("min")
    lap_level["lap_time_delta_to_fastest"] = lap_level["lap_time"] - fastest_per_race

    lap_level = lap_level[
        [
            "race_id",
            "track",
            "season",
            "date",
            "driver_id",
            "driver_name",
            "team",
            "lap_number",
            "lap_time",
            "lap_time_delta_to_fastest",
        ]
    ].sort_values(["race_id", "driver_id", "lap_number"])

    lap_level.to_csv(EXPORTS_DIR / "lap_level.csv", index=False)
    print(f"Wrote {len(lap_level):,} rows to exports/lap_level.csv")

    # =====================================================================
    # pitstop_level.csv
    # =====================================================================
    stops = pair_pit_stops(laps)
    pitstop_level = add_race_identity_columns(stops, race_dates)
    pitstop_level["driver_id"] = pitstop_level["Driver"]
    pitstop_level["driver_name"] = pitstop_level["Driver"].map(driver_name_map)
    pitstop_level["team"] = pitstop_level["Team"]

    results = drivers[["Driver", "Race", "Year", "FinishPosition"]].rename(
        columns={"FinishPosition": "finishing_position"}
    )
    pitstop_level = pitstop_level.merge(
        results, on=["Driver", "Race", "Year"], how="left"
    )

    pitstop_level = pitstop_level[
        [
            "race_id",
            "track",
            "season",
            "date",
            "driver_id",
            "driver_name",
            "team",
            "stop_number",
            "duration",
            "total_stops_in_race",
            "finishing_position",
        ]
    ].sort_values(["race_id", "driver_id", "stop_number"])

    pitstop_level.to_csv(EXPORTS_DIR / "pitstop_level.csv", index=False)
    print(f"Wrote {len(pitstop_level):,} rows to exports/pitstop_level.csv")

    # =====================================================================
    # driver_race_summary.csv
    # =====================================================================
    lap_stats = (
        lap_level.groupby(["race_id", "track", "season", "date", "driver_id", "driver_name", "team"])[
            "lap_time"
        ]
        .agg(avg_lap_time="mean", stdev_lap_time="std")
        .reset_index()
    )

    pit_stats = pitstop_level.groupby(["race_id", "driver_id"]).agg(
        avg_pit_stop_duration=("duration", "mean"),
        total_stops_in_race=("total_stops_in_race", "first"),
        finishing_position=("finishing_position", "first"),
    ).reset_index()

    driver_race_summary = lap_stats.merge(
        pit_stats, on=["race_id", "driver_id"], how="left"
    )
    driver_race_summary["total_stops_in_race"] = driver_race_summary[
        "total_stops_in_race"
    ].fillna(0).astype(int)

    # drivers who never appear in pitstop_level still need a finishing_position
    missing_pos = driver_race_summary["finishing_position"].isna()
    if missing_pos.any():
        fallback = results.rename(
            columns={"Driver": "driver_id", "Race": "track", "Year": "season"}
        )
        driver_race_summary = driver_race_summary.merge(
            fallback,
            on=["driver_id", "track", "season"],
            how="left",
            suffixes=("", "_fallback"),
        )
        driver_race_summary["finishing_position"] = driver_race_summary[
            "finishing_position"
        ].fillna(driver_race_summary["finishing_position_fallback"])
        driver_race_summary = driver_race_summary.drop(columns=["finishing_position_fallback"])

    driver_race_summary = driver_race_summary.sort_values(["race_id", "driver_id"])
    driver_race_summary.to_csv(EXPORTS_DIR / "driver_race_summary.csv", index=False)
    print(f"Wrote {len(driver_race_summary):,} rows to exports/driver_race_summary.csv")


if __name__ == "__main__":
    main()
