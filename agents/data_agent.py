"""
data_agent.py
-------------
Dispatches to the Snowflake-backed DataAgent (data_agent_snowflake.py) or
the legacy SQLite-backed DataAgent (data_agent_sqlite.py) based on the
DB_BACKEND env var. Defaults to "snowflake".

Set DB_BACKEND=sqlite in .env to fall back to the local data/pitwall.db
file while validating Snowflake results.
"""

import os

_BACKEND = os.getenv("DB_BACKEND", "snowflake").strip().lower()

if _BACKEND == "sqlite":
    from agents.data_agent_sqlite import DataAgent  # noqa: F401
elif _BACKEND == "snowflake":
    from agents.data_agent_snowflake import DataAgent  # noqa: F401
else:
    raise ValueError(
        f"Unknown DB_BACKEND={_BACKEND!r}. Expected 'snowflake' or 'sqlite'."
    )
