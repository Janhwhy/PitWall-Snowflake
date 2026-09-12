"""
app.py
------
PitWall — Streamlit front-end for the F1 RAG + multi-agent system.

Modes
-----
  Pre-Race Brief    — 5 auto-run questions cached in session state
  Live Q&A          — full chat interface powered by the Orchestrator
  Post-Race Debrief — placeholder (future: post-race summary agent)

Run:
    streamlit run app.py
"""

import pathlib
import sys

import streamlit as st

# ── Path bootstrap ───────────────────────────────────────────────────────────
ROOT_DIR = pathlib.Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# ── Page config (must be the very first Streamlit call) ──────────────────────
st.set_page_config(
    page_title="PitWall",
    page_icon="🏎️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* Base dark surface */
    [data-testid="stAppViewContainer"] {
        background-color: #0d0d0d;
    }

    /* Sidebar dark panel */
    [data-testid="stSidebar"] {
        background-color: #111111;
        border-right: 1px solid #2a2a2a;
    }
    [data-testid="stSidebar"] * {
        color: #e8e8e8 !important;
    }

    /* Sidebar branding */
    .pw-sidebar-title {
        font-size: 2rem;
        font-weight: 800;
        letter-spacing: -0.5px;
        color: #e8e8e8 !important;
        margin-bottom: 2px;
    }
    .pw-sidebar-subtitle {
        font-size: 0.78rem;
        color: #888 !important;
        letter-spacing: 0.04em;
        margin-bottom: 24px;
    }

    /* Section labels */
    .pw-label {
        font-size: 0.65rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #555 !important;
        margin-bottom: 6px;
        margin-top: 18px;
    }

    /* Thin divider */
    .pw-divider {
        border: none;
        border-top: 1px solid #2a2a2a;
        margin: 16px 0;
    }

    /* Main content typography */
    [data-testid="stAppViewContainer"] h1,
    [data-testid="stAppViewContainer"] h2,
    [data-testid="stAppViewContainer"] h3,
    [data-testid="stAppViewContainer"] p,
    [data-testid="stAppViewContainer"] li {
        color: #e8e8e8;
    }

    /* User chat bubble */
    .pw-bubble-user {
        background: #1e1e2e;
        border: 1px solid #2e2e4e;
        border-radius: 12px 12px 4px 12px;
        padding: 12px 16px;
        margin-bottom: 6px;
        color: #c4c9ff;
        font-size: 0.92rem;
        line-height: 1.5;
    }

    /* Bot chat bubble */
    .pw-bubble-bot {
        background: #141414;
        border: 1px solid #2a2a2a;
        border-radius: 12px 12px 12px 4px;
        padding: 14px 18px;
        margin-bottom: 4px;
        color: #e0e0e0;
        font-size: 0.92rem;
        line-height: 1.7;
    }

    /* Role label above each bubble */
    .pw-bubble-label {
        font-size: 0.62rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        margin-bottom: 6px;
    }
    .pw-bubble-label-user { color: #7c7fff; }
    .pw-bubble-label-bot  { color: #e10600; }

    /* Agent tag pills inside expander */
    .pw-agent-row {
        display: flex;
        align-items: center;
        gap: 10px;
        margin: 6px 0;
    }
    .pw-agent-pill {
        background: #1e1e1e;
        border: 1px solid #333;
        border-radius: 20px;
        padding: 3px 12px;
        font-size: 0.75rem;
        color: #aaa;
        font-family: monospace;
    }
    .pw-agent-chunks {
        font-size: 0.72rem;
        color: #555;
    }

    /* Placeholder banners */
    .pw-placeholder {
        background: #141414;
        border: 1px solid #2a2a2a;
        border-radius: 16px;
        padding: 60px 40px;
        text-align: center;
        margin-top: 40px;
    }
    .pw-placeholder h2 { font-size: 1.6rem; margin-bottom: 10px; }
    .pw-placeholder p  { color: #666; font-size: 0.9rem; }

    /* Text input */
    [data-testid="stTextInput"] input {
        background: #1a1a1a !important;
        color: #e8e8e8 !important;
        border: 1px solid #333 !important;
        border-radius: 10px !important;
        font-size: 0.92rem !important;
    }

    /* Primary button (Ask) */
    [data-testid="stButton"] button {
        background: #e10600 !important;
        color: #fff !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
        letter-spacing: 0.04em !important;
    }
    [data-testid="stButton"] button:hover {
        background: #c00500 !important;
    }

    /* Pre-Race Brief cards */
    .pw-card {
        background: #141414;
        border: 1px solid #2a2a2a;
        border-radius: 14px;
        padding: 24px 28px;
        margin-bottom: 20px;
    }
    .pw-card-header {
        font-size: 1.05rem;
        font-weight: 700;
        color: #e8e8e8;
        margin-bottom: 14px;
        padding-bottom: 10px;
        border-bottom: 1px solid #242424;
    }
    .pw-card-body {
        font-size: 0.88rem;
        color: #ccc;
        line-height: 1.75;
        white-space: pre-wrap;
    }

    /* Expander dark style */
    [data-testid="stExpander"] {
        background: #0f0f0f !important;
        border: 1px solid #222 !important;
        border-radius: 10px !important;
        margin-bottom: 20px;
    }
    [data-testid="stExpander"] summary {
        color: #666 !important;
        font-size: 0.8rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Session state ─────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    # Each entry: {"role": "user"|"bot", "text": str,
    #              "agent_results": list[dict]|None}
    st.session_state.messages = []

if "orchestrator" not in st.session_state:
    st.session_state.orchestrator = None   # lazy-loaded on first question

# Pre-Race Brief cache: None = not yet run, dict = keyed by section header
if "pre_brief_cache" not in st.session_state:
    st.session_state.pre_brief_cache = None

# Post-Race Debrief cache: None = not yet run, dict = keyed by section header
if "post_debrief_cache" not in st.session_state:
    st.session_state.post_debrief_cache = None


# ── Helper: load orchestrator once ───────────────────────────────────────────
def _get_orchestrator():
    if st.session_state.orchestrator is None:
        from agents.orchestrator import Orchestrator
        st.session_state.orchestrator = Orchestrator()
    return st.session_state.orchestrator


# ── Page renderers ────────────────────────────────────────────────────────────


# ── Pre-Race Brief definitions ────────────────────────────────────────────────
BRIEF_SECTIONS: list[tuple[str, str]] = [
    ("🔴 Tyre Strategy",        "What tyre strategies are available for this race?"),
    ("🌤️ Weather Impact",       "What does the weather mean for strategy?"),
    ("👀 Rivals to Watch",      "Who are the key rivals to watch?"),
    ("🗺️ Circuit Factors",      "What does the Monaco circuit mean for pit timing?"),
    ("✅ Recommended Strategy", "What is the recommended base race strategy?"),
]


def _run_brief() -> dict[str, dict]:
    """Run all 5 brief questions through the orchestrator sequentially.

    Returns a dict keyed by section header, each value being
    {"answer": str, "agent_results": list[dict]}.
    """
    orc = _get_orchestrator()
    results: dict[str, dict] = {}
    for header, question in BRIEF_SECTIONS:
        try:
            result = orc.run_with_details(question)
        except Exception:
            st.error("PitWall is unavailable right now — check your Groq API key")
            st.stop()
        results[header] = result
    return results


def _render_pre_race(race: str) -> None:
    st.markdown("## 🏁 Pre-Race Brief")
    st.markdown(
        f'<p style="color:#555;font-size:0.82rem;margin-top:-10px;">'
        f'Automated strategy briefing for <strong style="color:#999">{race}</strong>. '
        f'Results are cached — click <em>Refresh Brief</em> in the sidebar to re-run.</p>',
        unsafe_allow_html=True,
    )

    # Load from cache or run fresh
    if st.session_state.pre_brief_cache is None:
        with st.spinner("PitWall is thinking..."):
            st.session_state.pre_brief_cache = _run_brief()

    cache = st.session_state.pre_brief_cache

    # Render one card per section
    for header, _question in BRIEF_SECTIONS:
        entry         = cache.get(header, {})
        answer        = entry.get("answer", "No answer available.")
        agent_results = entry.get("agent_results", [])

        with st.container():
            st.markdown(
                f'<div class="pw-card">'
                f'<div class="pw-card-header">{header}</div>'
                f'<div class="pw-card-body">{answer}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            _render_agent_expander(agent_results)




# ── Post-Race Debrief definitions ────────────────────────────────────────────
DEBRIEF_SECTIONS: list[tuple[str, str]] = [
    (
        "⚠️ Suboptimal Calls",
        "Which pit stop calls were suboptimal and why?",
    ),
    (
        "📉 Tyre Degradation",
        "How did tyre degradation compare across the top 5 drivers?",
    ),
    (
        "🏆 Decisive Moment",
        "What was the most decisive strategic moment of the race?",
    ),
]

# Path to the pitstops CSV relative to this file
_PITSTOPS_CSV = ROOT_DIR / "data" / "laps" / "monaco_2025_pitstops.csv"


def _run_debrief() -> dict[str, dict]:
    """Run all 3 debrief questions through the orchestrator sequentially.

    Returns a dict keyed by section header, each value being
    {"answer": str, "agent_results": list[dict]}.
    """
    orc = _get_orchestrator()
    results: dict[str, dict] = {}
    for header, question in DEBRIEF_SECTIONS:
        try:
            result = orc.run_with_details(question)
        except Exception:
            st.error("PitWall is unavailable right now — check your Groq API key")
            st.stop()
        results[header] = result
    return results


def _render_post_race(race: str) -> None:
    import pandas as pd

    st.markdown("## 📊 Post-Race Debrief")
    st.markdown(
        f'<p style="color:#555;font-size:0.82rem;margin-top:-10px;">'
        f'Strategic review for <strong style="color:#999">{race}</strong>. '
        f'Results are cached — click <em>Refresh Debrief</em> in the sidebar to re-run.</p>',
        unsafe_allow_html=True,
    )

    # ── Run or serve from cache ───────────────────────────────────────────────
    if st.session_state.post_debrief_cache is None:
        with st.spinner("PitWall is thinking..."):
            st.session_state.post_debrief_cache = _run_debrief()

    cache = st.session_state.post_debrief_cache

    # ── One open expander per section ─────────────────────────────────────────
    for header, _question in DEBRIEF_SECTIONS:
        entry         = cache.get(header, {})
        answer        = entry.get("answer", "No answer available.")
        agent_results = entry.get("agent_results", [])

        with st.expander(header, expanded=True):
            st.markdown(
                f'<div class="pw-card-body" style="padding:4px 0 12px 0;">{answer}</div>',
                unsafe_allow_html=True,
            )
            _render_agent_expander(agent_results)

    # ── Raw pitstops dataframe ─────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🗂️ Raw Pit Stop Data")
    st.markdown(
        '<p style="color:#555;font-size:0.8rem;margin-top:-10px;">'
        'Underlying lap data used by the debrief analysis above.</p>',
        unsafe_allow_html=True,
    )

    if _PITSTOPS_CSV.exists():
        df = pd.read_csv(_PITSTOPS_CSV)

        # Clean up display: format timedelta-like columns as strings if needed
        for col in ("PitInTime", "PitOutTime"):
            if col in df.columns:
                df[col] = df[col].astype(str)

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Driver":     st.column_config.TextColumn("Driver",      width="small"),
                "LapNumber":  st.column_config.NumberColumn("Lap",       width="small", format="%d"),
                "PitInTime":  st.column_config.TextColumn("Pit In",      width="medium"),
                "PitOutTime": st.column_config.TextColumn("Pit Out",     width="medium"),
                "Compound":   st.column_config.TextColumn("Compound",    width="small"),
                "TyreLife":   st.column_config.NumberColumn("Tyre Life", width="small", format="%d laps"),
            },
        )
    else:
        st.warning(
            f"Pitstops CSV not found at `{_PITSTOPS_CSV}`. "
            "Run `python ingest/fetch_laps.py` first.",
            icon="⚠️",
        )



def _render_agent_expander(agent_results: list[dict]) -> None:
    """Render the 'Agents consulted' expander below a bot response."""
    if not agent_results:
        return
    with st.expander("🔍 Agents consulted"):
        for res in agent_results:
            agent_name  = res.get("agent", "unknown")
            chunks_used = res.get("chunks_used", 0)
            chunk_label = f"{chunks_used} chunk{'s' if chunks_used != 1 else ''}"
            st.markdown(
                f'<div class="pw-agent-row">'
                f'  <span class="pw-agent-pill">{agent_name}</span>'
                f'  <span class="pw-agent-chunks">{chunk_label} used</span>'
                f'</div>',
                unsafe_allow_html=True,
            )


def _render_live_qa(race: str) -> None:
    st.markdown("## 💬 Live Q&A")
    st.markdown(
        f'<p style="color:#555;font-size:0.82rem;margin-top:-10px;">'
        f'Ask anything about the <strong style="color:#999">{race}</strong> race. '
        f'Powered by the PitWall multi-agent system.</p>',
        unsafe_allow_html=True,
    )

    # ── Chat history ─────────────────────────────────────────────────────────
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.markdown(
                f'<div class="pw-bubble-user">'
                f'<div class="pw-bubble-label pw-bubble-label-user">You</div>'
                f'{msg["text"]}'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            # Bot message
            st.markdown(
                f'<div class="pw-bubble-bot">'
                f'<div class="pw-bubble-label pw-bubble-label-bot">PitWall</div>'
                f'{msg["text"]}'
                f'</div>',
                unsafe_allow_html=True,
            )
            # Show agent breakdown under each bot message
            agent_results = msg.get("agent_results") or []
            _render_agent_expander(agent_results)

    # ── Suggested questions ───────────────────────────────────────────────────
    st.markdown("<p style='font-size:0.8rem; color:#888; margin-bottom:8px;'>Suggested Questions:</p>", unsafe_allow_html=True)
    cols = st.columns(4)
    suggested_questions = [
        "When did Verstappen pit?",
        "Was there a safety car?",
        "How did tyre deg affect the top 3?",
        "What was the track temperature?"
    ]
    
    submitted_question = None
    for idx, (col, q) in enumerate(zip(cols, suggested_questions)):
        if col.button(q, key=f"sq_{idx}", use_container_width=True):
            submitted_question = q

    # ── Input row ─────────────────────────────────────────────────────────────
    col_input, col_btn = st.columns([5, 1])
    with col_input:
        user_input = st.text_input(
            label="Question",
            placeholder='e.g. "Should Norris have pitted earlier?"',
            label_visibility="collapsed",
            key="qa_input",
        )
    with col_btn:
        send = st.button("Ask", use_container_width=True)

    # ── Handle submission ─────────────────────────────────────────────────────
    if (send and user_input.strip()) or submitted_question:
        question = submitted_question if submitted_question else user_input.strip()
        st.session_state.messages.append(
            {"role": "user", "text": question, "agent_results": None}
        )

        # Lazy-load orchestrator and run
        with st.spinner("PitWall is thinking..."):
            try:
                orc = _get_orchestrator()
                result = orc.run_with_details(question)
                answer        = result["answer"]
                agent_results = result["agent_results"]
            except Exception:
                st.error("PitWall is unavailable right now — check your Groq API key")
                st.stop()

        st.session_state.messages.append(
            {"role": "bot", "text": answer, "agent_results": agent_results}
        )
        st.rerun()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="pw-sidebar-title">PitWall</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="pw-sidebar-subtitle">Your personal F1 pit wall</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<hr class="pw-divider">', unsafe_allow_html=True)

    st.markdown('<div class="pw-label">Race</div>', unsafe_allow_html=True)
    race = st.selectbox(
        label="Race selector",
        options=["Monaco 2025"],
        label_visibility="collapsed",
    )

    st.markdown('<div class="pw-label">Data Sources</div>', unsafe_allow_html=True)
    try:
        from utils.snowflake_client import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        counts = {}
        for name, table in [("Laps", "laps_chunks"), ("Weather", "weather_chunks"),
                             ("Radio", "radio_chunks"), ("Pit Stops", "pitstops_chunks")]:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            counts[name] = cursor.fetchone()[0]
        conn.close()
        c1, c2 = st.columns(2)
        c1.metric("Laps", counts["Laps"])
        c2.metric("Weather", counts["Weather"])
        c3, c4 = st.columns(2)
        c3.metric("Radio", counts["Radio"])
        c4.metric("Pit Stops", counts["Pit Stops"])
    except Exception:
        st.markdown("<p style='font-size:0.8rem;color:#888;'>Metrics unavailable</p>", unsafe_allow_html=True)

    st.markdown('<div class="pw-label">Mode</div>', unsafe_allow_html=True)
    mode = st.radio(
        label="Navigation",
        options=["🏁 Pre-Race Brief", "💬 Live Q&A", "📊 Post-Race Debrief"],
        label_visibility="collapsed",
    )

    st.markdown('<hr class="pw-divider">', unsafe_allow_html=True)

    # Context-sensitive sidebar actions
    if mode == "🏁 Pre-Race Brief":
        if st.button("🔄 Refresh Brief", use_container_width=True):
            st.session_state.pre_brief_cache = None
            st.rerun()
    elif mode == "📊 Post-Race Debrief":
        if st.button("🔄 Refresh Debrief", use_container_width=True):
            st.session_state.post_debrief_cache = None
            st.rerun()
    else:
        if st.button("🗑️ Clear chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    st.markdown(
        '<p style="font-size:0.65rem;color:#444;text-align:center;margin-top:12px;">'
        'Powered by FastF1 · ChromaDB · Groq</p>',
        unsafe_allow_html=True,
    )

# ── Route to selected mode ────────────────────────────────────────────────────
if mode == "🏁 Pre-Race Brief":
    _render_pre_race(race)

elif mode == "💬 Live Q&A":
    _render_live_qa(race)

elif mode == "📊 Post-Race Debrief":
    _render_post_race(race)
