-- Cortex Search services replacing the 4 ChromaDB collections
-- (laps, weather, radio, pitstops — see utils/vectorstore.py).
-- Auto-embeds chunk_text on creation and keeps itself in sync via TARGET_LAG.

CREATE OR REPLACE CORTEX SEARCH SERVICE laps_search
    ON chunk_text
    ATTRIBUTES driver, lap_number, compound, race, year
    WAREHOUSE = COMPUTE_WH
    TARGET_LAG = '1 hour'
    AS (
        SELECT chunk_id, chunk_text, driver, lap_number, compound, race, year
        FROM laps_chunks
    );

CREATE OR REPLACE CORTEX SEARCH SERVICE weather_search
    ON chunk_text
    ATTRIBUTES race, year
    WAREHOUSE = COMPUTE_WH
    TARGET_LAG = '1 hour'
    AS (
        SELECT chunk_id, chunk_text, window_start, window_end, race, year
        FROM weather_chunks
    );

CREATE OR REPLACE CORTEX SEARCH SERVICE pitstops_search
    ON chunk_text
    ATTRIBUTES driver, lap_number, compound, race, year
    WAREHOUSE = COMPUTE_WH
    TARGET_LAG = '1 hour'
    AS (
        SELECT chunk_id, chunk_text, driver, lap_number, compound,
               pit_in_time, pit_out_time, tyre_life, race, year
        FROM pitstops_chunks
    );

CREATE OR REPLACE CORTEX SEARCH SERVICE radio_search
    ON chunk_text
    ATTRIBUTES speaker, filename, race, year
    WAREHOUSE = COMPUTE_WH
    TARGET_LAG = '1 hour'
    AS (
        SELECT chunk_id, chunk_text, speaker, filename, race, year
        FROM radio_chunks
    );
