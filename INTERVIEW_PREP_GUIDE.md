# PitWall — Interview Preparation Guide

This is a speaking guide for the version of PitWall in this repository. It is deliberately honest: describe what the application does today, distinguish it from planned improvements, and do not imply that a historical-data prototype supplies live race decisions.

## 1. The 30-second explanation

> PitWall is a full-stack Formula 1 strategy-analysis application. A user can browse race weekends, results, standings and schedule data, then ask natural-language questions such as why a pit stop made sense or how weather affected tyre strategy. I designed it around two data paths: exact factual screens use direct SQLite queries, while open-ended strategy questions use retrieval-augmented generation and specialised agents over lap, pit-stop, weather and radio data. This gives users natural explanations without using an LLM for numbers that should be exact.

If the interviewer is non-technical, say:

> Think of it as a digital race engineer’s briefing tool. It gathers detailed race records, turns them into a searchable knowledge base, uses the right specialist for a question, and presents both the supporting analysis and the final recommendation in a web dashboard.

## 2. The problem and the product

F1 strategy data is scattered and difficult to interpret. Lap times, tyre ages, pit stops, weather and radio messages each tell only part of the story. A normal dashboard is good at showing exact numbers but makes a user assemble the conclusion themselves. A generic chatbot gives a fluent answer but can invent facts.

PitWall addresses both problems:

- It presents normal structured views: season calendar, standings, race results, qualifying grid, pit-stop log and weather summary.
- It provides a strategy Q&A experience for questions requiring interpretation.
- It constrains the language model to retrieved project data and shows which specialist reports informed the response.

The current dataset is historical, primarily covering selected 2025 and 2026 events. It is an analysis and briefing prototype, **not** a live, production race-control system or a predictive simulator.

## 3. What the user can do

- Browse a dashboard with the next event, standings, latest-race information and weather.
- Browse the full calendar and only select race weekends for which deep data was actually ingested.
- Open a race weekend for classification, deterministic race statistics, qualifying, a pre-race brief and a post-race debrief.
- Ask a free-form question in the strategy chat and inspect the individual agent reports.
- See a graceful online/offline indicator for the optional local `f1-dash` live-map service.

The React app has routes for `/`, `/races`, `/races/:year/:round`, `/standings` and `/chat`.

## 4. Architecture at a glance

```text
FastF1 / Ergast data + optional radio audio
              |
              v
offline ingestion scripts
  CSV/JSON files --> SQLite (exact relational facts)
                 --> chunk + embed --> ChromaDB (semantic search)
                                         |
React/Vite <--> FastAPI <----------------+
                    |
       exact screens: SQL queries
       strategy Q&A: router --> specialist agents (parallel)
                               --> Groq LLM synthesis
```

The key sentence to remember is: **SQLite answers “what happened exactly?”; ChromaDB plus the LLM helps explain “what does the data suggest and why?”**

## 5. Data flow, in plain English

1. Offline scripts collect completed-session data using FastF1: laps, driver information, pit events, weather and qualifying. Separate scripts collect season schedules and championship standings. Radio audio can be downloaded and transcribed locally.
2. The pipeline stores structured records in SQLite. That is ideal for exact filters, joins, counts, averages and rankings.
3. It also converts useful records into readable snippets, for example one snippet for a driver’s lap or one pit-stop event. The snippets are embedded as vectors and stored in ChromaDB.
4. When a user asks a strategy question, the backend interprets which domains are relevant, finds semantically similar snippets for the selected race/year, asks specialist agents to interpret only that context, and has a final model merge the reports.
5. The frontend receives typed JSON and renders the response, including the specialist breakdown.

## 6. Technical architecture: enough detail for an interview

### Frontend

- **React 19 + TypeScript + Vite**: a fast single-page application with type checking and production bundling.
- **React Router** handles client-side routes. `vercel.json` rewrites requests to `index.html`, so direct navigation to a nested route does not become a 404.
- **Context API** provides shared race metadata and backend-health state. It seeds Monaco as a usable fallback if the API is unavailable, then loads the actual available races.
- `src/lib/api.ts` centralises the API types, fetch calls, error handling and a 30-second abort timeout. That avoids duplicated HTTP logic across components.
- The visual layer uses a dark motorsport theme, circuit SVG paths, driver/team theme helpers and reusable panels. Circuit drawings are simplified UI illustrations rather than telemetry-grade track geometry.

### Backend

- **FastAPI** exposes typed REST endpoints. Pydantic request/response models form a clear API contract with the TypeScript client.
- `api/main.py` registers health, strategy, schedule and standings routers and configures CORS for the separately deployed frontend.
- Deterministic routes query the local SQLite file. Examples: `/race-stats`, `/race-results`, `/pit-stops` and `/weather-summary`.
- Strategy routes—`POST /ask`, `GET /brief` and `GET /debrief`—use the agent orchestrator. The brief/debrief endpoints cache their fixed-question results in process memory per race label.

### Storage

SQLite stores relational tables: `laps`, `pitstops`, `drivers`, `qualifying` and `weather`. At review time the database contained about 30.6k lap rows, 4.3k weather rows, 1,013 pit-stop rows, and roughly 550 driver/qualifying rows.

ChromaDB has four collections: `laps`, `weather`, `pitstops` and `radio`. It persists locally in `vectorstore/`, while SQLite is in `data/pitwall.db`.

### AI / RAG pipeline

- **Chunking:** each lap and pit stop becomes a compact textual record with metadata such as driver, lap number, compound, race and year. Weather is summarised in ten-row windows; radio is parsed into speaker blocks.
- **Embedding:** `BAAI/bge-small-en-v1.5` produces normalised 384-dimensional local embeddings. Normalising makes cosine-distance similarity meaningful and comparable.
- **Retrieval:** the question is embedded once, then queried across selected collections. The API filters by race/year metadata before selecting results, applies a distance threshold, sorts by lowest distance and caps the combined context to 30 snippets.
- **Generation:** Groq-hosted `openai/gpt-oss-20b` is the default fast model for routing and specialist answers. The larger `openai/gpt-oss-120b` is used for final synthesis and text-to-SQL because correctness matters more in those steps.

## 7. What “multi-agent” means here

Do not oversell it as autonomous agents that independently plan for hours. In this project, agents are focused analysis modules with separate data access and instructions:

| Agent | Data it can use | Responsibility |
|---|---|---|
| Tyre | laps, pit stops | compounds, stint length, degradation, pit timing |
| Weather | weather | track conditions and tyre implications |
| Radio | radio | strategy intent and driver/team communications |
| Rivals | laps, pit stops | relative pace, undercut/overcut threats |
| Circuit | radio, laps | incidents and track-position implications |
| Data | SQLite | exact numerical, aggregation and lookup questions |

The orchestrator asks an LLM router to select one to three semantic specialists and **also includes the DataAgent**. It runs selected agents concurrently with a `ThreadPoolExecutor`, so independent LLM calls overlap instead of running sequentially. It then sends the reports to a synthesis model. The synthesis prompt tells the model to prefer the direct SQL report when it fully answers a factual question.

Why not use one giant prompt? Separation gives focused context, prevents unrelated data from crowding the prompt, makes the UI more inspectable, and lets the system choose SQL for exact facts. The trade-off is extra model calls, latency and operational cost.

## 8. RAG explained simply

RAG means “retrieve before generating.” Rather than asking an LLM to answer from its general training data, PitWall first searches its own F1 records and places the most relevant records in the prompt.

An interview-ready explanation:

> The model is not my database. SQLite and ChromaDB are the sources of truth. RAG supplies relevant evidence at question time, which makes the answer more grounded and lets the knowledge base be refreshed without fine-tuning a model.

Why both vector search and SQL?

- SQL is exact but requires a known schema and structured question. “Which driver had the fastest lap?” is a direct query.
- Vector search handles wording variation and unstructured context. “What did the team radio indicate about the tyre decision?” is a semantic retrieval problem.
- The DataAgent translates quantitative natural-language questions to SQL, while the deterministic pages use handwritten SQL for critical known metrics.

## 9. Example request walkthrough

Question: “Why was the pit-stop timing risky in Monaco 2025?”

1. The client calls `POST /ask` with the question and `race: "Monaco 2025"`.
2. The backend parses that label into `race="Monaco"` and `year=2025`.
3. The router is likely to select tyre/circuit/rivals specialists, plus the always-included data agent.
4. The tyre and rivals agents retrieve only Monaco 2025 lap and pit-stop snippets. The circuit agent searches lap/radio snippets in the same scope.
5. Agents produce evidence-constrained reports. They should say they lack data rather than speculate when the snippets do not support a claim.
6. The synthesis model removes duplication and returns one concise answer. The API also returns individual reports and their chunk counts for transparency.

## 10. Important endpoint families

| Purpose | Endpoints | Why the design matters |
|---|---|---|
| Health and availability | `/`, `/status`, `/f1dash/status` | lightweight liveness and vector-store visibility |
| AI strategy | `POST /ask`, `GET /brief`, `GET /debrief` | narrative analysis, not a source for exact aggregates |
| Race facts | `/races`, `/race-stats`, `/race-results`, `/pit-stops`, `/weather-summary` | direct SQLite reads, so known facts are deterministic |
| Calendar | `/schedule`, `/schedule/next` | full calendar including future events from static JSON |
| Championship | `/standings/drivers`, `/standings/constructors` | cached/ingested season standings |

`/races` deliberately lists only race weekends with ingested lap data. The calendar endpoint is broader and can show future events. That prevents the question UI from offering a weekend it cannot actually analyse.

## 11. Data ingestion and updates

The core bulk runner is `ingest/run_all_seasons.py`:

1. Read or fetch the season schedule.
2. For each completed event, fetch lap, pit-stop, driver and weather data.
3. Convert CSV records to chunks with race/year metadata.
4. Embed chunks locally in batches.
5. Upsert them into the relevant Chroma collection.

`utils/db_manager.py` builds the SQLite database from the CSV files. `reingest.py` deletes the four Chroma collections and rebuilds them, which is useful after a data-shape or embedding change. Upsert IDs include race/year and driver/lap or window values, making re-ingestion idempotent for the same record keys.

Schedule and standings are stored as JSON because the frontend mainly reads them as whole documents; lap-level data goes into SQLite because it benefits from relational queries.

## 12. Deployment story

- The FastAPI backend is configured for **Render** via `render.yaml`.
- The React frontend is configured for **Vercel**.
- The frontend receives the backend origin through `VITE_API_BASE_URL`.
- `GROQ_API_KEY` is a server-side environment variable; it must never be in client code or committed to Git.
- Deployment uses a reduced API dependency list. It installs CPU-only PyTorch first to avoid a large CUDA installation on a small Render instance.
- The project ships the prebuilt SQLite and Chroma data with the backend, so normal deployment does not need to run data ingestion.

## 13. Strong design choices to defend

### Separating facts from explanations

Exact stats use written SQL endpoints. This is faster and much safer than asking an LLM to count rows or choose a fastest lap. The RAG path is reserved for ambiguous, explanatory questions.

### Race/year metadata filters

Semantic similarity alone can retrieve a template-like lap record from another event. Filtering Chroma metadata by race/year before ranking prevents cross-race contamination.

### Local embeddings and persisted vector store

Embeddings are generated locally during ingestion and stored persistently. That avoids paying an embedding API per question and keeps retrieval available as long as the local model/data are available.

### Parallel specialist work

Specialists do not depend on one another, so concurrent execution lowers response latency compared with serial calls. The final synthesis waits for the set of available results and tolerates an individual specialist failure.

### Transparent agent results

The API returns `agents_consulted` and `chunks_used`, not only a black-box answer. This is useful for debugging and for user trust.

### Typed contracts end to end

Pydantic response models on FastAPI and TypeScript interfaces in the API client make schema changes visible during development rather than silently breaking a component.

## 14. Limitations to state confidently

Being able to say these voluntarily makes you sound stronger, not weaker.

1. **Historical / partial data:** not every race has every data source. Radio coverage is particularly limited in the current repository, so the radio agent should often return insufficient data.
2. **Not live telemetry or a prediction engine:** the optional `f1-dash` integration currently checks a local service and displays a map experience; it is not an end-to-end live-data ingestion system.
3. **RAG is not proof:** nearest-neighbour retrieval supplies a relevant sample, not an exhaustive dataset. That is why exact counts and rankings should be performed in SQL.
4. **In-memory caching:** brief/debrief caching is per backend process. It disappears after a restart and does not coordinate across multiple instances.
5. **Latency/cost:** multi-agent routing plus several LLM requests can be slower and costlier than one call.
6. **Prototype security/scale:** there is no user authentication, application rate limiting, distributed cache, background job queue or production observability stack.
7. **Circuit specialisation mismatch:** the UI supports multiple circuits, while `CircuitAgent`'s prompt is explicitly Monaco-focused. Generalising the prompt and adding circuit metadata would be a priority before presenting it as universal circuit expertise.

## 15. Improvements I would make next

Use this structure: problem, concrete engineering change, benefit.

- **Reliable read-only Text-to-SQL:** do not rely only on checking the first SQL word. Use SQLite's authorizer or a query parser and a read-only connection, restrict tables/row limits and log generated SQL. This closes edge cases such as a data-changing statement hidden behind a `WITH` clause.
- **Citations:** return chunk IDs, source fields and confidence/retrieval distance with each strategy claim so users can inspect evidence rather than only the agent name.
- **Better evaluation:** create a labelled question set covering factual, cross-race, no-data and adversarial-prompt cases; measure retrieval recall, SQL correctness, groundedness, latency and answer usefulness. Existing tests are mostly smoke scripts, not a full automated test suite.
- **Hybrid retrieval:** combine vector similarity with metadata/keyword filters and reranking; fetch adjacent laps for temporal context rather than isolated single-lap snippets.
- **Operational resilience:** add timeouts per agent, structured logs/traces, metrics, rate limits and a fallback answer when Groq is unavailable.
- **Scalability:** move from a committed local SQLite/Chroma bundle to managed PostgreSQL plus a managed vector database or pgvector, add indexes on `(Race, Year, Driver)`, and refresh data through scheduled jobs.
- **Security:** replace wildcard production CORS with the deployed frontend allowlist, keep secrets solely in a secret manager, add authentication if the product becomes multi-user, and validate payload limits.
- **Live usefulness:** ingest official live/near-live feeds, version data by session timestamp, and make the UI disclose freshness.

## 16. High-probability interview questions and answers

### “Why use RAG instead of fine-tuning?”

The knowledge changes with every race, while fine-tuning is costly and hard to update or audit. RAG lets me refresh the data independently, retrieve the relevant event context, and keep model training separate from factual F1 records.

### “Why use a vector database when you already have SQLite?”

SQLite is ideal when I can express the question as a precise query. A user may ask the same strategy question in many ways, especially around radio and narrative context. Vectors retrieve semantically related snippets without requiring exact keywords. I use SQL for exhaustive facts and vectors for explanatory evidence.

### “How do you reduce hallucination?”

I scope retrieval to race/year, use focused collections per agent, instruct agents to answer only from supplied context and say they lack data otherwise, and use deterministic SQL for exact stats. It reduces risk, but I would not claim it eliminates hallucinations; citations and formal evaluation are the next step.

### “How does the multi-agent layer improve things?”

It limits each analysis to the right data domain—weather data for weather implications, radio for communications, SQL for totals—then consolidates the reports. It is a modular routing pattern, not magic intelligence. The trade-off is more calls and latency.

### “Why always invoke the DataAgent?”

The LLM router can miss questions that are really aggregations, such as “which team pitted the most?” SQLite can answer those precisely. The DataAgent self-limits on non-queryable questions, so I accept small additional cost for better factual coverage.

### “How do you protect the database from LLM-generated SQL?”

Currently, the prompt requests one read-only query and the code rejects queries not beginning with `SELECT` or `WITH`, while SQLite runs against local project data. I would strengthen this with SQLite’s authorizer/read-only mode or parsed SQL allowlisting; string validation alone is not a complete security boundary.

### “Why is the final model larger?”

Specialists can use a faster model because they do a narrow evidence extraction. The synthesis and SQL-generation steps reconcile information or generate executable syntax, where an error is more costly, so the code uses the larger Groq model there.

### “What happens if there is no relevant data?”

Retrieval can return no chunks. Agent prompts instruct an exact insufficient-data response, and the orchestrator returns it when no specialist report can answer. Some deterministic endpoints return empty/null typed fields rather than inventing values.

### “How does your API remain compatible with the frontend?”

FastAPI's Pydantic models define backend request/response shapes, and matching TypeScript interfaces are centralised in the frontend API module. Client calls, error handling and timeouts also live there instead of being scattered across components.

### “What would you do for scale?”

Keep the hybrid architecture but move data to Postgres with indexes and a managed vector store/pgvector, cache common answers in Redis, run ingestion in scheduled background workers, add queues/rate limits/observability, and horizontally scale stateless API instances.

### “What did you test?”

The repository includes smoke scripts for chunking, vector-store behaviour, RAG and agents. I also ran a production frontend type-check/build during this review successfully. I would add automated unit tests for parsing and SQL routes, integration tests with a small seeded database, and mocked-LLM evaluation tests before calling it production-ready.

## 17. Questions you should ask yourself before the interview

- Can I explain the difference between a lap, stint, tyre life, undercut and overcut in simple terms?
- Can I walk through the example request in section 9 without notes?
- Can I name the four vector collections and the five SQLite tables?
- Can I explain why a fastest-lap result belongs in SQL, while “why was the strategy risky?” belongs in RAG?
- Can I describe one limitation and one specific technical improvement without saying “I would use AI better”?
- Can I state the deployment split: Render backend, Vercel frontend, env var for API URL, Groq key server-side?

## 18. Do not say these things

- “It predicts the winning strategy.” It currently analyses historical/project data; it is not a validated prediction model.
- “The AI directly queries all data.” Semantic agents see a retrieved subset; the DataAgent is the SQL path.
- “It has real-time telemetry.” The code has an optional local-service status check, not a complete real-time pipeline.
- “It never hallucinates.” Say that it has grounding controls and known limitations.
- “It is fully production-ready.” It is a strong full-stack prototype; production needs the improvements in section 15.

## 19. File map for last-minute revision

| Area | Start here |
|---|---|
| API composition | `api/main.py`, `api/models.py` |
| Q&A entry point | `api/routes/ask.py` |
| Agent orchestration | `agents/orchestrator.py` |
| Exact analytics | `api/routes/race_stats.py`, `api/routes/results.py`, `api/routes/pitstops.py` |
| RAG pipeline | `utils/chunker.py`, `utils/embedder.py`, `utils/retriever.py`, `utils/vectorstore.py`, `utils/groq_client.py` |
| Text-to-SQL | `agents/data_agent.py` |
| Data refresh | `ingest/run_all_seasons.py`, `ingest/fetch_laps.py`, `utils/db_manager.py`, `reingest.py` |
| React entry / routes | `frontend/src/App.tsx` |
| Shared client state | `frontend/src/context/AppContext.tsx` |
| HTTP client | `frontend/src/lib/api.ts` |
| Deployment | `README.md`, `render.yaml`, `frontend/vercel.json` |

## 20. Best final answer when asked “what did you learn?”

> The biggest lesson was that a useful AI application is mostly about data boundaries and system design, not simply calling a model. I learned to decide which answers should come from deterministic queries, how to make unstructured data searchable with embeddings, how to scope and inspect AI context, and how to expose the whole workflow through a typed full-stack application. I also learned where the prototype needs stronger evaluation, security and operational controls before production.
