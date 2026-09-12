"""
migrate_to_snowflake.py
------------------------
One-shot migration: copies the 5 structured SQLite tables and materializes
the 4 RAG chunk sets (currently built in-memory by utils/chunker.py for
ChromaDB) into their Snowflake equivalents.

Idempotent: TRUNCATEs each target table before loading, so safe to re-run
after re-ingesting new race data.

Usage
-----
    python scripts/migrate_to_snowflake.py
"""

import pathlib
import re
import sys

import pandas as pd
from snowflake.connector.pandas_tools import write_pandas

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from utils.snowflake_client import get_connection  # noqa: E402
from utils.chunker import (  # noqa: E402
    chunk_lap_data, chunk_weather_data,
    chunk_radio_transcripts, chunk_pitstop_data,
)

SQLITE_PATH = ROOT_DIR / "data" / "pitwall.db"
STRUCTURED_TABLES = ["laps", "pitstops", "weather", "drivers", "qualifying"]
LAPS_DIR = ROOT_DIR / "data" / "laps"
HISTORY_DIR = ROOT_DIR / "data" / "history"
RADIO_DIR = ROOT_DIR / "data" / "radio" / "transcripts"


def _parse_filename(filename: str):
    """Mirrors utils/db_manager.py's parse_filename exactly."""
    match = re.match(r"^([a-z _]+)_(\d{4})", filename)
    if match:
        return match.group(1).title(), int(match.group(2))
    return "Unknown", 0


def _discover_races() -> list[tuple[str, int]]:
    """One (race_name, year) pair per base laps CSV (excludes _pitstops/_drivers/_quali)."""
    races = []
    for f in sorted(LAPS_DIR.glob("*.csv")):
        if "_pitstops" in f.name or "_drivers" in f.name or "_quali" in f.name:
            continue
        races.append(_parse_filename(f.name))
    return races


def migrate_structured_tables(con) -> None:
    import sqlite3

    sqlite_con = sqlite3.connect(SQLITE_PATH)
    try:
        for table in STRUCTURED_TABLES:
            df = pd.read_sql(f"SELECT * FROM {table}", sqlite_con)
            if df.empty:
                print(f"[SKIP] {table}: 0 rows in SQLite")
                continue

            cur = con.cursor()
            cur.execute(f"TRUNCATE TABLE {table}")

            success, nchunks, nrows, _ = write_pandas(
                con, df, table.upper(), quote_identifiers=False
            )
            print(f"[OK] {table}: loaded {nrows} rows (success={success})")
    finally:
        sqlite_con.close()


def _chunks_to_df(chunks: list[dict], id_fn, extra_cols: list[str]) -> pd.DataFrame:
    rows = []
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        row = {"chunk_id": id_fn(meta), "chunk_text": chunk["text"]}
        for col in extra_cols:
            row[col] = meta.get(col)
        rows.append(row)
    return pd.DataFrame(rows)


def migrate_chunk_tables(con) -> None:
    races = _discover_races()
    print(f"[INFO] Discovered {len(races)} race/year combos: {races}")

    all_lap_chunks: list[dict] = []
    all_weather_chunks: list[dict] = []
    all_pit_chunks: list[dict] = []

    for race_name, year in races:
        all_lap_chunks.extend(chunk_lap_data(race_name=race_name, year=year))

        try:
            all_weather_chunks.extend(chunk_weather_data(race_name=race_name, year=year))
        except FileNotFoundError as exc:
            print(f"[SKIP] weather for {race_name} {year}: {exc}")

        try:
            all_pit_chunks.extend(chunk_pitstop_data(race_name=race_name, year=year))
        except FileNotFoundError as exc:
            print(f"[SKIP] pitstops for {race_name} {year}: {exc}")

    # ── laps_chunks ──────────────────────────────────────────────────────
    df = _chunks_to_df(
        all_lap_chunks,
        id_fn=lambda m: f"{str(m.get('race')).lower()}_{m.get('year')}_{m.get('driver')}_lap{m.get('lap_number')}",
        extra_cols=["driver", "lap_number", "compound", "race", "year"],
    )
    _load_chunk_table(con, "laps_chunks", df)

    # ── weather_chunks ───────────────────────────────────────────────────
    df = _chunks_to_df(
        all_weather_chunks,
        id_fn=lambda m: f"{str(m.get('race')).lower()}_{m.get('year')}_weather_window_{m.get('window_start')}",
        extra_cols=["window_start", "window_end", "race", "year"],
    )
    _load_chunk_table(con, "weather_chunks", df)

    # ── pitstops_chunks ──────────────────────────────────────────────────
    df = _chunks_to_df(
        all_pit_chunks,
        id_fn=lambda m: f"{str(m.get('race')).lower()}_{m.get('year')}_pit_{m.get('driver')}_lap{m.get('lap_number')}",
        extra_cols=["driver", "lap_number", "compound", "pit_in_time",
                    "pit_out_time", "tyre_life", "race", "year"],
    )
    _load_chunk_table(con, "pitstops_chunks", df)

    # ── radio_chunks (only monaco_2025 transcript exists) ───────────────
    radio_chunks = chunk_radio_transcripts(race_name="Monaco", year=2025)
    counters: dict[str, int] = {}

    def _radio_id(m):
        fn = m.get("filename", "radio")
        idx = counters.get(fn, 0)
        counters[fn] = idx + 1
        race, year = m.get("race"), m.get("year")
        if race and year:
            return f"{str(race).lower()}_{year}_{fn}_{idx}"
        return f"{fn}_{idx}"

    df = _chunks_to_df(
        radio_chunks,
        id_fn=_radio_id,
        extra_cols=["speaker", "filename", "race", "year"],
    )
    _load_chunk_table(con, "radio_chunks", df)


def _load_chunk_table(con, table_name: str, df: pd.DataFrame) -> None:
    if df.empty:
        print(f"[SKIP] {table_name}: 0 chunks generated")
        return

    cur = con.cursor()
    cur.execute(f"TRUNCATE TABLE {table_name}")

    success, nchunks, nrows, _ = write_pandas(
        con, df, table_name.upper(), quote_identifiers=False
    )
    print(f"[OK] {table_name}: loaded {nrows} rows (success={success})")


def main() -> None:
    con = get_connection()
    try:
        print("\n=== Migrating structured tables ===")
        migrate_structured_tables(con)

        print("\n=== Migrating RAG chunk tables ===")
        migrate_chunk_tables(con)
    finally:
        con.close()

    print("\n[DONE] Migration complete.")


if __name__ == "__main__":
    main()
