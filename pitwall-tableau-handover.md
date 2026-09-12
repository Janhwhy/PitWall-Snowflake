# PitWall → Tableau dashboard: data export handover

## Goal
Export clean, pre-aggregated CSV(s) from the PitWall SQLite database so they can be connected directly to Tableau Public with minimal calculated-field work. This feeds a single-page dashboard on **driver performance/consistency** and **pit stop strategy/efficiency**.

## Source tables to pull from
- `drivers` (id, name, team)
- `races` (id, track, date, season)
- `lap_times` (race_id, driver_id, lap_number, lap_time)
- `pit_stops` (race_id, driver_id, stop_number, duration)
- `results` (race_id, driver_id, finishing_position)

## Output: two flat CSVs

### 1. `lap_level.csv`
One row per driver per lap. Join `lap_times` with `drivers` and `races`.

Columns:
- `race_id`, `track`, `season`, `date`
- `driver_id`, `driver_name`, `team`
- `lap_number`, `lap_time`
- `lap_time_delta_to_fastest` — lap_time minus the fastest lap in that race (so laps are comparable across different tracks)

### 2. `pitstop_level.csv`
One row per pit stop. Join `pit_stops` with `drivers`, `races`, and `results`.

Columns:
- `race_id`, `track`, `season`, `date`
- `driver_id`, `driver_name`, `team`
- `stop_number`, `duration`
- `total_stops_in_race` — count of stops for that driver in that race
- `finishing_position` — from `results`, joined on race_id + driver_id

## Pre-aggregations to compute in the export script (not in Tableau)
- Per driver per race: `avg_lap_time`, `stdev_lap_time` (consistency metric)
- Per driver per race: `avg_pit_stop_duration`

These can either be extra columns appended to the two CSVs above, or a third small `driver_race_summary.csv` with one row per driver per race — whichever is cleaner to join in Tableau (prefer the third option if it avoids repeating aggregate values across many lap/pit-stop rows).

## Data cleaning requirements
- Handle nulls (e.g. DNF drivers with no finishing position — keep the row, mark position as null/DNF rather than dropping it)
- Normalize driver and team names (consistent casing/spelling across tables)
- Ensure `lap_time` and `duration` are numeric (seconds, consistent unit)
- Standardize date format (ISO 8601)

## Dashboard this feeds (for context, not required to build)
Single-page layout: 3 KPI cards (avg finishing position, avg pit stop duration, lap time consistency) + 5 charts:
1. Lap time trend per driver (line)
2. Teammate head-to-head avg lap time (bar, filtered to same team)
3. Driver consistency spread (box plot)
4. Pit stop duration by team (bar)
5. Pit stop time vs. finishing position (scatter, full width)

## Deliverable
A Python (or SQL) script in the PitWall repo that connects to the SQLite DB, runs the joins/aggregations above, and writes `lap_level.csv`, `pitstop_level.csv`, and `driver_race_summary.csv` to a local `/exports` folder — ready to drag into Tableau Public as a data source.
