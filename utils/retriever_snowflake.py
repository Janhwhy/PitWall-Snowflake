"""
retriever_snowflake.py
------------------------
Cortex Search equivalent of retriever_chromadb.py — same public API
(`retrieve`, `ALL_COLLECTIONS`) and same return shape (text, metadata,
distance, collection), so utils/rag.py and prompt_builder.py need no
changes regardless of which backend utils/retriever.py dispatches to.

Distance here is `1 - cosine_similarity` (lower = more similar), matching
the "lower is better" convention the ChromaDB path used — the absolute
scale differs from ChromaDB's (different embedding model: Snowflake's
snowflake-arctic-embed-m-v1.5 vs. bge-small-en-v1.5), so distance_threshold
defaults may need re-tuning against real queries.
"""

import json
from typing import Any

from utils.snowflake_client import get_connection

ALL_COLLECTIONS: list[str] = ["laps", "weather", "radio", "pitstops"]

# collection -> (search service name, extra columns to fetch beyond chunk_text)
_SERVICES: dict[str, tuple[str, list[str]]] = {
    "laps":     ("laps_search",     ["driver", "lap_number", "compound", "race", "year"]),
    "weather":  ("weather_search",  ["window_start", "window_end", "race", "year"]),
    "radio":    ("radio_search",    ["speaker", "filename", "race", "year"]),
    "pitstops": ("pitstops_search", ["driver", "lap_number", "compound",
                                      "pit_in_time", "pit_out_time", "tyre_life",
                                      "race", "year"]),
}


def _build_filter(race: str | None, year: int | None) -> dict[str, Any] | None:
    conditions = []
    if race:
        conditions.append({"@eq": {"race": race}})
    if year:
        conditions.append({"@eq": {"year": year}})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"@and": conditions}


def retrieve(
    query: str,
    collections: list[str] | None = None,
    top_k: int = 15,
    distance_threshold: float = 0.80,
    race: str | None = None,
    year: int | None = None,
) -> list[dict[str, Any]]:
    """
    Search the requested Cortex Search services and return matching chunks.
    Signature and return shape match utils.retriever_chromadb.retrieve.
    """
    if not query or not query.strip():
        raise ValueError("'query' must be a non-empty string.")

    target_collections = collections if collections is not None else ALL_COLLECTIONS

    unknown = set(target_collections) - set(ALL_COLLECTIONS)
    if unknown:
        raise ValueError(
            f"Unknown collection(s): {sorted(unknown)}. Valid: {ALL_COLLECTIONS}"
        )

    filt = _build_filter(race, year)
    scope_label = f" (scoped to race={race!r}, year={year!r})" if filt else ""
    print(f"[INFO] retrieve (snowflake): searching {target_collections} for: {query[:80]!r}{scope_label}")

    results: list[dict[str, Any]] = []

    con = get_connection()
    try:
        cur = con.cursor()
        for col_name in target_collections:
            service_name, extra_cols = _SERVICES[col_name]

            payload: dict[str, Any] = {
                "query": query.strip(),
                "columns": ["chunk_text"] + extra_cols,
                "limit": top_k,
            }
            if filt is not None:
                payload["filter"] = filt

            cur.execute(
                "SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW(%s, %s)",
                (service_name, json.dumps(payload)),
            )
            raw = json.loads(cur.fetchone()[0])

            for hit in raw.get("results", []):
                cosine_sim = hit.get("@scores", {}).get("cosine_similarity", 0.0)
                distance = 1.0 - float(cosine_sim)
                if distance > distance_threshold:
                    continue

                metadata = {k: hit[k] for k in extra_cols if k in hit}
                metadata["source"] = col_name

                results.append({
                    "text":       hit.get("chunk_text", ""),
                    "metadata":   metadata,
                    "distance":   distance,
                    "collection": col_name,
                })
    finally:
        con.close()

    results.sort(key=lambda r: r["distance"])
    results = results[:30]

    print(f"[INFO] retrieve (snowflake): returned {len(results)} chunk(s) (threshold={distance_threshold})")
    return results


if __name__ == "__main__":
    print("=== retriever_snowflake.py smoke test ===\n")
    test_query = "When did Verstappen pit?"
    hits = retrieve(test_query, race="Monaco", year=2025)
    if not hits:
        print("[WARN] No results found.")
    else:
        print(f"Found {len(hits)} result(s):\n")
        for i, hit in enumerate(hits[:5], start=1):
            print(f"  [{i}] col={hit['collection']} dist={hit['distance']:.4f} meta={hit['metadata']} text={hit['text'][:80]!r}")
