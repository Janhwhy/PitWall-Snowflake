-- Structured tables, mirroring data/pitwall.db exactly (see utils/db_manager.py).
-- Run once against PITWALL.PUBLIC before running scripts/migrate_to_snowflake.py.

CREATE TABLE IF NOT EXISTS laps (
    Driver          VARCHAR,
    Team            VARCHAR,
    LapNumber       FLOAT,
    LapTime         VARCHAR,
    Compound        VARCHAR,
    TyreLife        FLOAT,
    Position        FLOAT,
    PitInTime       VARCHAR,
    PitOutTime      VARCHAR,
    Race            VARCHAR,
    Year            NUMBER,
    LapTimeSeconds  FLOAT
);

CREATE TABLE IF NOT EXISTS pitstops (
    Driver      VARCHAR,
    Team        VARCHAR,
    LapNumber   FLOAT,
    PitInTime   VARCHAR,
    PitOutTime  VARCHAR,
    Compound    VARCHAR,
    TyreLife    FLOAT,
    Race        VARCHAR,
    Year        NUMBER
);

CREATE TABLE IF NOT EXISTS weather (
    AirTemp        FLOAT,
    Humidity       FLOAT,
    Pressure       FLOAT,
    Rainfall       NUMBER,
    TrackTemp      FLOAT,
    WindDirection  NUMBER,
    WindSpeed      FLOAT,
    Race           VARCHAR,
    Year           NUMBER
);

CREATE TABLE IF NOT EXISTS drivers (
    Driver          VARCHAR,
    FullName        VARCHAR,
    Team            VARCHAR,
    FinishPosition  FLOAT,
    Race            VARCHAR,
    Year            NUMBER
);

CREATE TABLE IF NOT EXISTS qualifying (
    Driver         VARCHAR,
    FullName       VARCHAR,
    Team           VARCHAR,
    GridPosition   FLOAT,
    Q1             FLOAT,
    Q2             FLOAT,
    Q3             FLOAT,
    Race           VARCHAR,
    Year           NUMBER
);

-- Chunk tables backing the 4 Cortex Search services (replaces ChromaDB
-- collections of the same name — see utils/chunker.py for the text format
-- these mirror, and utils/vectorstore.py for the current Chroma schema).

CREATE TABLE IF NOT EXISTS laps_chunks (
    chunk_id     VARCHAR PRIMARY KEY,
    chunk_text   VARCHAR,
    driver       VARCHAR,
    lap_number   NUMBER,
    compound     VARCHAR,
    race         VARCHAR,
    year         NUMBER
);

CREATE TABLE IF NOT EXISTS weather_chunks (
    chunk_id      VARCHAR PRIMARY KEY,
    chunk_text    VARCHAR,
    window_start  NUMBER,
    window_end    NUMBER,
    race          VARCHAR,
    year          NUMBER
);

CREATE TABLE IF NOT EXISTS pitstops_chunks (
    chunk_id      VARCHAR PRIMARY KEY,
    chunk_text    VARCHAR,
    driver        VARCHAR,
    lap_number    NUMBER,
    compound      VARCHAR,
    pit_in_time   VARCHAR,
    pit_out_time  VARCHAR,
    tyre_life     VARCHAR,
    race          VARCHAR,
    year          NUMBER
);

CREATE TABLE IF NOT EXISTS radio_chunks (
    chunk_id  VARCHAR PRIMARY KEY,
    chunk_text VARCHAR,
    speaker   VARCHAR,
    filename  VARCHAR,
    race      VARCHAR,
    year      NUMBER
);
