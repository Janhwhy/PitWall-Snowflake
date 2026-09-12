"""
retriever.py
------------
Pure semantic retrieval: embeds the user query and finds the most similar
chunks across one or more ChromaDB collections (laps, weather, radio, pitstops).

No LLM pre-processing. No metadata filters. Just fast, reliable vector search.
"""

import pathlib
import sys
from typing import Any

# ── Path bootstrap ──────────────────────────────────────────────────────────
ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from utils.embedder import embed_chunks
from utils.vectorstore import (
    get_laps_collection,
    get_weather_collection,
    get_radio_collection,
    get_pitstops_collection,
)

# ── Constants ───────────────────────────────────────────────────────────────
ALL_COLLECTIONS: list[str] = ["laps", "weather", "radio", "pitstops"]

_COLLECTION_GETTERS: dict[str, Any] = {
    "laps":     get_laps_collection,
    "weather":  get_weather_collection,
    "radio":    get_radio_collection,
    "pitstops": get_pitstops_collection,
}


def _build_where(race: str | None, year: int | None) -> dict[str, Any] | None:
    """
    Build a ChromaDB `where` filter for the given race/year, if any.

    ChromaDB (>=0.5) requires a single top-level operator, so combining two
    equality conditions must go through an explicit "$and" — a plain
    {"race": ..., "year": ...} dict raises "Expected where to have exactly
    one operator".
    """
    conditions = []
    if race:
        conditions.append({"race": {"$eq": race}})
    if year:
        conditions.append({"year": {"$eq": year}})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def retrieve(
    query: str,
    collections: list[str] | None = None,
    top_k: int = 15,
    distance_threshold: float = 0.80,
    race: str | None = None,
    year: int | None = None,
) -> list[dict[str, Any]]:
    """
    Embed `query` and return the top matching chunks from the requested collections.

    Parameters
    ----------
    query : str
        Natural-language search question.
    collections : list[str] | None
        Subset of collections to search. Defaults to all four.
    top_k : int
        Number of results to request from each collection.
    distance_threshold : float
        Maximum cosine distance to accept (lower = stricter).
    race : str | None
        If given, scope the search to chunks tagged with this race
        (e.g. "Monaco"). Without this, nearest-neighbour search runs over
        the whole multi-season corpus and can surface chunks from the
        wrong race for template-heavy data like lap/pit rows.
    year : int | None
        If given, scope the search to chunks tagged with this season.

    Returns
    -------
    list[dict]
        Sorted list of matching chunks, each with keys:
        text, metadata, distance, collection.
    """
    if not query or not query.strip():
        raise ValueError("'query' must be a non-empty string.")

    target_collections = collections if collections is not None else ALL_COLLECTIONS

    unknown = set(target_collections) - set(ALL_COLLECTIONS)
    if unknown:
        raise ValueError(
            f"Unknown collection(s): {sorted(unknown)}. Valid: {ALL_COLLECTIONS}"
        )

    # 1. Embed the query once
    embedded = embed_chunks([{"text": query.strip(), "metadata": {}}])
    query_vector = embedded[0]["embedding"]

    where = _build_where(race, year)
    scope_label = f" (scoped to race={race!r}, year={year!r})" if where else ""
    print(f"[INFO] retrieve: searching {target_collections} for: {query[:80]!r}{scope_label}")

    # 2. Query each collection
    results: list[dict[str, Any]] = []

    for col_name in target_collections:
        collection = _COLLECTION_GETTERS[col_name]()

        if collection.count() == 0:
            print(f"[INFO] retrieve: '{col_name}' collection is empty, skipping.")
            continue

        n_results = min(top_k, collection.count())

        query_kwargs: dict[str, Any] = {
            "query_embeddings": [query_vector],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where is not None:
            query_kwargs["where"] = where

        raw = collection.query(**query_kwargs)

        documents = raw["documents"][0]
        metadatas = raw["metadatas"][0]
        distances = raw["distances"][0]

        for text, metadata, distance in zip(documents, metadatas, distances):
            if distance <= distance_threshold:
                results.append({
                    "text":       text,
                    "metadata":   metadata,
                    "distance":   distance,
                    "collection": col_name,
                })

    # 3. Sort by relevance (lowest distance = most similar)
    results.sort(key=lambda r: r["distance"])

    # 4. Keep top 30 overall
    results = results[:30]

    print(f"[INFO] retrieve: returned {len(results)} chunk(s) (threshold={distance_threshold})")
    return results


if __name__ == "__main__":
    print("=== retriever.py smoke test ===\n")
    test_query = "When did Verstappen pit?"
    hits = retrieve(test_query)
    if not hits:
        print("[WARN] No results found. Is the database populated?")
    else:
        print(f"Found {len(hits)} result(s):\n")
        for i, hit in enumerate(hits[:5], start=1):
            print(f"  [{i}] col={hit['collection']} dist={hit['distance']:.4f} meta={hit['metadata']} text={hit['text'][:80]!r}")
