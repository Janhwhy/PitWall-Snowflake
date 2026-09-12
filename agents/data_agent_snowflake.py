"""
data_agent_snowflake.py
------------------------
Snowflake equivalent of data_agent_sqlite.py — same public API
(DataAgent.run(query, race, year) -> dict), same Text-to-SQL approach,
just querying Snowflake's PITWALL.PUBLIC schema instead of the local
SQLite file. Column/table names are unquoted-uppercase in Snowflake, but
that's transparent here since Snowflake folds unquoted identifiers
case-insensitively — mixed-case SQL the LLM writes still resolves fine.
"""

import json
from typing import Any

from agents.base_agent import BaseAgent
from utils.groq_client import ask_groq
from utils.snowflake_client import get_connection

SQL_MODEL = "openai/gpt-oss-120b"
MAX_SQL_ATTEMPTS = 2

_STRUCTURED_TABLES = ["laps", "pitstops", "weather", "drivers", "qualifying"]


class DataAgent(BaseAgent):
    """
    Agent specializing in analytical questions using Text-to-SQL against
    Snowflake.
    """

    def __init__(self) -> None:
        super().__init__(name="data_agent", collections=[])  # Does not use vector search

    def _get_schema(self, cursor) -> str:
        """Retrieves the Snowflake schema for the structured tables."""
        schema = []
        for table_name in _STRUCTURED_TABLES:
            cursor.execute(f"DESCRIBE TABLE {table_name}")
            columns = cursor.fetchall()
            # DESCRIBE TABLE: column 0 = name, column 1 = type
            col_details = [f"{col[0]} ({col[1]})" for col in columns]
            schema.append(f"Table: {table_name}\nColumns: {', '.join(col_details)}")

        return "\n\n".join(schema)

    def _get_reference_values(self, cursor) -> str:
        """
        Same purpose as the SQLite version: hand the LLM the real distinct
        Team/Compound values so free-text mentions map onto exact stored
        strings instead of silently returning zero rows.
        """
        try:
            cursor.execute("SELECT DISTINCT Team FROM laps WHERE Team IS NOT NULL ORDER BY Team")
            teams = [row[0] for row in cursor.fetchall()]
        except Exception:
            teams = []

        try:
            cursor.execute("SELECT DISTINCT Compound FROM laps WHERE Compound IS NOT NULL ORDER BY Compound")
            compounds = [row[0] for row in cursor.fetchall()]
        except Exception:
            compounds = []

        lines = []
        if teams:
            lines.append(f"Valid Team values (use EXACTLY as written, map colloquial names to these): {', '.join(teams)}")
        if compounds:
            lines.append(f"Valid Compound values: {', '.join(compounds)}")
        lines.append(
            "The 'laps'/'pitstops' tables only store 3-letter Driver codes (e.g. 'ANT'), never full names. "
            "If the question asks for a driver's name (e.g. 'who won', 'who is VER'), JOIN against the "
            "'drivers' table (Driver=Code) to get FullName — never guess a name from your own knowledge, "
            "since driver-code assignments for this season may not match what you'd expect."
        )
        return "\n".join(lines)

    def run(self, query: str, race: str | None = None, year: int | None = None) -> dict[str, Any]:
        """
        Translates query to SQL, executes it against Snowflake, and returns
        the result. Same parameters/return shape as the SQLite version.
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()
            schema_str = self._get_schema(cursor)
            reference_str = self._get_reference_values(cursor)
        except Exception as e:
            return {
                "agent": self.name,
                "answer": f"Error connecting to database: {e}",
                "chunks_used": 0,
            }

        # ── 1. Text to SQL ──────────────────────────────────────────────────
        context_line = ""
        if race or year:
            context_line = (
                f"\nCurrent race context: Race={race!r}, Year={year!r}. "
                "Filter on the Race/Year columns using this context UNLESS the "
                "question explicitly asks to compare across races or seasons.\n"
            )

        sql_system_prompt = (
            "You are a SQL expert for a Formula 1 database hosted on Snowflake. "
            "Your task is to write a Snowflake SQL query to answer the user's question.\n\n"
            f"Here is the database schema:\n{schema_str}\n"
            f"{reference_str}\n"
            f"{context_line}\n"
            "RULES:\n"
            "1. Output ONLY the raw SQL query. Do not wrap it in markdown code blocks like ```sql.\n"
            "2. Ensure the query is valid Snowflake SQL syntax, and ONLY reference the tables/columns listed above — never invent a table or column that isn't in the schema.\n"
            "3. For drivers, ALWAYS use the standard 3-letter F1 abbreviation (e.g. 'VER' for Verstappen, 'LEC' for Leclerc, 'HAM' for Hamilton) in the WHERE clause.\n"
            "4. For teams, map whatever the user wrote to the closest entry in the 'Valid Team values' list above and use that EXACT string (e.g. 'Red Bull' -> 'Red Bull Racing', 'Merc' -> 'Mercedes'). Never filter on a team string that isn't in that list.\n"
            "5. Write a read-only SELECT query ONLY. Never write INSERT, UPDATE, DELETE, DROP, ALTER, MERGE, COPY, or any other statement that modifies data or schema.\n"
            "6. If the question cannot be meaningfully answered by querying this schema — it's asking for reasons, opinions, narrative explanation, or anything not present as queryable data — output exactly the single token: UNANSWERABLE (nothing else).\n"
            "7. Otherwise, return exactly the SQL query and nothing else."
        )

        # ── 2 & 3. Generate SQL, guard it, execute — retrying once with the
        # error fed back if the first attempt is invalid or fails to run.
        sql_query_raw = ""
        db_results_str = ""
        last_error: str | None = None

        for attempt in range(1, MAX_SQL_ATTEMPTS + 1):
            user_prompt = query
            if last_error:
                user_prompt = (
                    f"{query}\n\n"
                    f"Your previous query failed:\n{sql_query_raw}\n"
                    f"Error: {last_error}\n"
                    "Fix the query and try again. Only use tables/columns from the schema above."
                )

            sql_query_raw = ask_groq(
                system_prompt=sql_system_prompt,
                user_prompt=user_prompt,
                model=SQL_MODEL,
            ).strip()

            # Clean up in case the LLM returned markdown blocks anyway
            if sql_query_raw.startswith("```sql"):
                sql_query_raw = sql_query_raw[6:]
            if sql_query_raw.startswith("```"):
                sql_query_raw = sql_query_raw[3:]
            if sql_query_raw.endswith("```"):
                sql_query_raw = sql_query_raw[:-3]
            sql_query_raw = sql_query_raw.strip()

            if sql_query_raw.strip(" .").upper() == "UNANSWERABLE":
                conn.close()
                return {
                    "agent": self.name,
                    "answer": "I don't have enough data to answer that.",
                    "chunks_used": 0,
                }

            # Guard against non-SELECT / multi-statement SQL — never trust
            # LLM-generated SQL from free-form user input to be read-only
            # on its own.
            first_word = sql_query_raw.split(None, 1)[0].upper() if sql_query_raw else ""
            stripped = sql_query_raw.rstrip().rstrip(";")
            if first_word not in ("SELECT", "WITH") or ";" in stripped:
                conn.close()
                return {
                    "agent": self.name,
                    "answer": (
                        "I can only run read-only SELECT queries against the F1 database, "
                        "and the generated query didn't qualify. Please rephrase the question."
                    ),
                    "chunks_used": 0,
                }

            try:
                cursor.execute(stripped)
                results = cursor.fetchall()
                col_names = [description[0] for description in cursor.description] if cursor.description else []

                if not results:
                    db_results_str = "Query returned no results."
                else:
                    rows_str = [
                        ", ".join(f"{col}={val}" for col, val in zip(col_names, row))
                        for row in results[:50]  # Limit to 50 rows for context
                    ]
                    db_results_str = "\n".join(rows_str)
                last_error = None
                break
            except Exception as e:
                last_error = str(e)
                if attempt == MAX_SQL_ATTEMPTS:
                    conn.close()
                    return {
                        "agent": self.name,
                        "answer": f"Failed to execute SQL query: {sql_query_raw}\nError: {e}",
                        "chunks_used": 0,
                    }

        conn.close()

        # ── 4. Return raw results — no synthesis LLM call here ───────────────
        answer = f"SQL: {sql_query_raw}\nResult:\n{db_results_str}"

        return {
            "agent": self.name,
            "answer": answer,
            "chunks_used": 0,
        }
