"""
orchestrator.py
---------------
Defines the Orchestrator class, which acts as the main routing and synthesis controller
in the multi-agent PitWall system. It routes queries to relevant specialist agents based on
keywords, runs them in parallel using ThreadPoolExecutor, and synthesizes a final,
unified race strategy answer using the Groq LLM.
"""

import concurrent.futures
from typing import Any

from agents.base_agent import BaseAgent
from agents.tyre_agent import TyreAgent
from agents.weather_agent import WeatherAgent
from agents.radio_agent import RadioAgent
from agents.rivals_agent import RivalsAgent
from agents.circuit_agent import CircuitAgent
from agents.data_agent import DataAgent
from utils.groq_client import ask_groq
from utils.snowflake_client import get_connection

# Reconciling multiple (sometimes overlapping, sometimes conflicting)
# specialist reports into one correct final answer needs more reasoning than
# the fast default model reliably gives — it has been observed to ignore an
# unambiguous data_agent answer in favour of an unrelated driver code
# mentioned in passing by another report. Use the larger model for this
# final synthesis step specifically.
SYNTHESIS_MODEL = "openai/gpt-oss-120b"


class Orchestrator:
    """
    Main coordinator that routes user queries to specialized agents,
    orchestrates their parallel execution, and synthesizes their responses.
    """

    def __init__(self) -> None:
        """Initialize and pre-instantiate all specialist agents."""
        self.agents = {
            "tyre": TyreAgent(),
            "weather": WeatherAgent(),
            "radio": RadioAgent(),
            "rivals": RivalsAgent(),
            "circuit": CircuitAgent(),
            "data": DataAgent(),
        }

    def route(self, query: str) -> list[BaseAgent]:
        """
        Route the query to relevant specialist agents based on LLM semantic routing.

        Parameters
        ----------
        query : str
            The user question/query text.

        Returns
        -------
        list of BaseAgent
            The selected specialist agents to run.
        """
        system_prompt = (
            "You are an intelligent router for an F1 Strategy RAG system.\n"
            "Your job is to determine which specialist agents should handle the user's query.\n"
            "The available agents are:\n"
            "- tyre: for tyre strategy, degradation, stints, compounds, pit stops, pit timing\n"
            "- weather: for rain, temperature, track conditions, and weather\n"
            "- radio: for team radio transcripts and driver communications\n"
            "- rivals: for competitor analysis, gaps between drivers, overcuts, undercuts\n"
            "- circuit: for track incidents, safety cars, overtakes, yellow flags\n"
            "- data: ONLY for explicit math questions like 'how many', 'average', 'total', 'fastest lap time'\n\n"
            "RULES:\n"
            "1. Output a comma-separated list of agent names only (e.g., tyre, weather).\n"
            "2. Do not include any other text.\n"
            "3. Select at least 1 and at most 3 agents.\n"
            "4. For questions about pit stops or pit timing, always include 'tyre'.\n"
            "5. When in doubt, prefer the semantic agents (tyre, rivals, circuit, radio) over data."
        )
        
        response = ask_groq(system_prompt=system_prompt, user_prompt=query)
        selected_names = [name.strip().lower() for name in response.split(',')]

        matched = []
        for name in selected_names:
            if name in self.agents and self.agents[name] not in matched:
                matched.append(self.agents[name])

        # Always call at least 1 agent. Fallback to tyre agent (most general).
        if not matched:
            matched = [self.agents["tyre"]]

        # Always try the data agent too, regardless of what the LLM router
        # picked. Whether a question is "quantitative enough" for SQL is a
        # judgment call the router gets wrong often (e.g. "which team
        # pitted the most?" was routed to tyre/rivals and never reached
        # data_agent, even though it's a plain COUNT/GROUP BY). DataAgent
        # is cheap (one local SQLite query) and self-limiting — it reports
        # "I don't have enough data to answer that." for anything outside
        # the schema, so including it unconditionally costs a bit of
        # latency but never hurts an answer that's actually semantic.
        if self.agents["data"] not in matched:
            matched.append(self.agents["data"])

        return matched

    @staticmethod
    def _get_driver_legend(race: str | None, year: int | None) -> str:
        """
        Look up real Code -> FullName (Team) pairs from the drivers table so
        the synthesis step can correctly expand a driver code mentioned by
        any agent, instead of the LLM guessing a name from pretrained bias
        (which gets it wrong whenever this season's grid doesn't match what
        it expects — e.g. rookies, mid-career team switches).

        Scoped to the given race/year when provided; otherwise returns every
        distinct code seen across the whole database (still a small list —
        roughly one grid's worth of drivers).
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()
            if race and year:
                cursor.execute(
                    "SELECT DISTINCT Driver, FullName, Team FROM drivers WHERE Race = %s AND Year = %s ORDER BY Driver",
                    (race, year),
                )
            else:
                cursor.execute("SELECT DISTINCT Driver, FullName, Team FROM drivers ORDER BY Driver")
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            return ""

        if not rows:
            return ""

        pairs = "; ".join(f"{code} = {name} ({team})" for code, name, team in rows)
        return f"Driver code legend (use these EXACT names, do not guess): {pairs}"

    def _run_agents(self, query: str, race: str | None, year: int | None) -> list[dict]:
        """Route the query and run every selected agent in parallel."""
        selected_agents = self.route(query)

        agent_results: list[dict] = []
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {executor.submit(agent.run, query, race, year): agent for agent in selected_agents}
            for future in concurrent.futures.as_completed(futures):
                agent = futures[future]
                try:
                    result = future.result()
                    agent_results.append(result)
                except Exception as exc:
                    print(f"[ERROR] Orchestrator: Agent '{agent.name}' failed with exception: {exc}")

        return agent_results

    def _synthesize(
        self,
        query: str,
        agent_results: list[dict],
        race: str | None,
        year: int | None,
    ) -> str:
        """Combine every agent's report into one final, unified answer."""
        driver_legend = self._get_driver_legend(race, year)
        legend_line = f"\n{driver_legend}\n" if driver_legend else ""

        system_prompt = (
            "You are PitWall, the master F1 race strategy orchestrator. "
            "Your job is to synthesize reports from various specialist strategy agents into "
            "a single, unified, cohesive, and precise answer for the user.\n\n"
            f"{legend_line}"
            "RULES:\n"
            "1. Base your answer ONLY on the provided specialist reports.\n"
            "2. Ensure all insights are consolidated logically, removing duplicate or contradictory information.\n"
            "3. Write one clean, professional, direct answer to the user's question. Do NOT mention the specialist "
            "agents by name, do NOT use bracketed tags like [tyre_agent], and do NOT describe your internal process "
            "— the agent breakdown is already shown to the user separately. Just answer the question.\n"
            "4. If the specialist reports contain insufficient information to answer the question, or if all reports returned "
            "\"I don't have enough data to answer that.\", you must output exactly: \"I don't have enough data to answer that.\"\n"
            "5. One specialist report comes from a direct SQL query against the database, not semantic search — for "
            "any factual lookup (counts, totals, averages, \"which X had the most/least\", \"who won\", \"who finished "
            "Nth\", race results), that report's answer is authoritative and complete. When it directly and fully "
            "answers the question, state ONLY that answer (reworded naturally) — do not append, blend in, or "
            "reconcile it with specific claims (which driver, which lap, which team) from a different report, even "
            "as \"supporting\" detail. The other reports were built from a small retrieved sample and cannot see "
            "team affiliation at all, so any team-specific detail they add is unverified and often wrong; silently "
            "drop it rather than repeating it.\n"
            "6. Drivers are referred to by 3-letter codes in the reports (e.g. VER, ANT). If the driver legend above "
            "is present, use it to state the driver's real full name in your answer. If no legend is given or a code "
            "isn't in it, keep the code as-is — never invent a name.\n"
            "7. Be concise and write in a professional, race-engineer style."
        )

        reports_str = ""
        for res in agent_results:
            agent_name = res.get("agent", "unknown_agent")
            answer = res.get("answer", "No response.")
            chunks = res.get("chunks_used", 0)
            reports_str += f"### Specialist Report from {agent_name} (using {chunks} context chunks):\n"
            reports_str += f"{answer}\n\n"

        user_prompt = (
            "## Specialist Reports Received\n\n"
            f"{reports_str}"
            "---\n\n"
            "## User Question\n"
            f"{query}\n\n"
            "Please synthesize the specialist reports into a single, unified answer."
        )

        return ask_groq(system_prompt=system_prompt, user_prompt=user_prompt, model=SYNTHESIS_MODEL)

    def run(self, query: str, race: str | None = None, year: int | None = None) -> str:
        """
        Coordinate routing, parallel execution of selected agents, and response synthesis.

        Parameters
        ----------
        query : str
            The user question/query text.
        race : str | None
            If given, scope every agent's retrieval to this race (e.g. "Monaco").
        year : int | None
            If given, scope every agent's retrieval to this season.

        Returns
        -------
        str
            The synthesized final response from the Orchestrator.
        """
        agent_results = self._run_agents(query, race, year)
        if not agent_results:
            return "I don't have enough data to answer that."
        return self._synthesize(query, agent_results, race, year)

    def run_with_details(
        self,
        query: str,
        race: str | None = None,
        year: int | None = None,
    ) -> tuple[str, list[dict]]:
        """
        Like run(), but also returns the raw per-agent result dictionaries so
        callers can surface individual agent answers and chunk counts.

        Parameters
        ----------
        query : str
            The user question/query text.
        race : str | None
            If given, scope every agent's retrieval to this race (e.g. "Monaco").
        year : int | None
            If given, scope every agent's retrieval to this season.

        Returns
        -------
        tuple of (str, list of dict)
            - The synthesised final answer string.
            - A list of agent result dicts, each containing "agent", "answer",
              and "chunks_used" keys (same structure as BaseAgent.run() output).
        """
        agent_results = self._run_agents(query, race, year)
        if not agent_results:
            return "I don't have enough data to answer that.", []
        return self._synthesize(query, agent_results, race, year), agent_results
