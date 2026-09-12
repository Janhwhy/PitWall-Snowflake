"""
retriever.py
------------
Dispatches to the Snowflake Cortex Search backend (retriever_snowflake.py)
or the legacy ChromaDB backend (retriever_chromadb.py) based on the
RAG_BACKEND env var. Defaults to "snowflake".

Set RAG_BACKEND=chromadb in .env to fall back to the original local
vector store while validating Cortex Search results.
"""

import os

_BACKEND = os.getenv("RAG_BACKEND", "snowflake").strip().lower()

if _BACKEND == "chromadb":
    from utils.retriever_chromadb import retrieve, ALL_COLLECTIONS  # noqa: F401
elif _BACKEND == "snowflake":
    from utils.retriever_snowflake import retrieve, ALL_COLLECTIONS  # noqa: F401
else:
    raise ValueError(
        f"Unknown RAG_BACKEND={_BACKEND!r}. Expected 'snowflake' or 'chromadb'."
    )
