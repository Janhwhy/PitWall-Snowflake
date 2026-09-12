import { useState, useEffect, useRef } from 'react';
import { useAppData } from '../context/AppContext';
import type { AgentResult } from '../lib/api';
import { askQuestion } from '../lib/api';
import CircuitGlassSelector from '../components/CircuitGlassSelector';
import MarkdownLite from '../components/MarkdownLite';

const AGENT_STYLE: Record<
  string,
  { color: string; icon: string; name: string; tag: string }
> = {
  tyre_agent: { color: '#e10600', icon: 'tire_repair', name: 'Tyre Analyst', tag: 'Degradation & Compound Model' },
  weather_agent: { color: '#0ea5e9', icon: 'cloudy_snowing', name: 'Weather Desk', tag: 'Micro-climate Radar' },
  radio_agent: { color: '#f59e0b', icon: 'radio', name: 'Radio Monitoring', tag: 'Driver & Pit Transmissions' },
  rivals_agent: { color: '#a855f7', icon: 'groups', name: 'Rival Intel', tag: 'Gap & Overcut Simulator' },
  circuit_agent: { color: '#10b981', icon: 'map', name: 'Circuit Map', tag: 'Track Surface & Apex Metrics' },
  data_agent: { color: '#f97316', icon: 'query_stats', name: 'Data Engine', tag: 'ChromaDB Vector Store' },
};

interface Message {
  id: string;
  role: 'user' | 'ai';
  text: string;
  agents?: AgentResult[];
  timestamp: string;
  raceContext: string;
  chunksUsed?: number;
  isError?: boolean;
}

const SAMPLE_PROMPTS = [
  'What is the optimal pit strategy window for Medium to Hard tyres?',
  'Will weather or rain impact tyre degradation on Laps 15 to 30?',
  'Compare Hamilton vs Russell stint pace and undercut probability.',
  'Analyze safety car probability and optimal pit stop timing.',
];

const LOADING_STAGES = [
  'Routing query to specialist agents',
  'Querying ChromaDB vector stores',
  'Cross-referencing telemetry & radio logs',
  'Synthesizing final strategy answer',
];

function timeNow() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
}

function AgentCard({ agent }: { agent: AgentResult }) {
  const [expanded, setExpanded] = useState(false);
  const style = AGENT_STYLE[agent.agent] ?? {
    color: '#e10600',
    icon: 'memory',
    name: agent.agent,
    tag: 'Specialist',
  };

  return (
    <div className="rounded-xl bg-surface-container-lowest/80 border border-border-rim overflow-hidden transition-colors hover:border-f1-red/40">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="w-full flex items-center justify-between gap-2 p-3 text-left cursor-pointer"
      >
        <div className="flex items-center gap-2 min-w-0">
          <span
            className="material-symbols-outlined text-base flex-none"
            style={{ color: style.color }}
          >
            {style.icon}
          </span>
          <div className="min-w-0">
            <div className="font-headline-md text-white text-xs font-bold uppercase truncate">
              {style.name}
            </div>
            <div className="text-[10px] text-secondary font-telemetry-sm truncate">
              {agent.chunks_used} chunks retrieved
            </div>
          </div>
        </div>
        <span
          className={`material-symbols-outlined text-secondary text-lg flex-none transition-transform duration-200 ${
            expanded ? 'rotate-180' : ''
          }`}
        >
          expand_more
        </span>
      </button>

      <div
        className={`grid transition-all duration-200 ease-out ${
          expanded ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'
        }`}
      >
        <div className="overflow-hidden">
          <div className="px-3 pb-3 pt-0 text-xs text-secondary leading-relaxed border-t border-border-rim/60 mt-0 max-h-64 overflow-y-auto">
            <div className="pt-3">
              <MarkdownLite text={agent.answer} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Chat() {
  const { latestRace, status } = useAppData();
  const [selectedYear, setSelectedYear] = useState<'2025' | '2026'>('2026');
  const [selectedRace, setSelectedRace] = useState(latestRace);

  useEffect(() => {
    setSelectedYear(String(latestRace.year) as '2025' | '2026');
    setSelectedRace(latestRace);
  }, [latestRace]);

  const raceLabel = `${selectedRace.country} ${selectedRace.year}`;

  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome-1',
      role: 'ai',
      text: `PitWall Multi-Agent Strategy RAG Engine online for ${raceLabel}. I'm connected to ChromaDB vector stores containing telemetry, lap times, pit stop logs, and pit wall radio transmissions. Ask any strategic query to trigger specialist agents.`,
      timestamp: timeNow(),
      raceContext: raceLabel,
      chunksUsed: (status.laps || 0) + (status.weather || 0) + (status.pitstops || 0) + (status.radio || 0),
    },
  ]);

  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingStage, setLoadingStage] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  useEffect(() => {
    if (!loading) {
      setLoadingStage(0);
      return;
    }
    const interval = setInterval(() => {
      setLoadingStage((s) => Math.min(s + 1, LOADING_STAGES.length - 1));
    }, 2200);
    return () => clearInterval(interval);
  }, [loading]);

  const send = async (questionText: string) => {
    const q = questionText.trim();
    if (!q || loading) return;

    const userMsg: Message = {
      id: `${Date.now()}-u`,
      role: 'user',
      text: q,
      timestamp: timeNow(),
      raceContext: raceLabel,
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const res = await askQuestion(q, raceLabel);
      const totalChunks = res.agents_consulted.reduce((acc, a) => acc + (a.chunks_used || 0), 0);

      const aiMsg: Message = {
        id: `${Date.now()}-a`,
        role: 'ai',
        text: res.final_answer,
        agents: res.agents_consulted,
        timestamp: timeNow(),
        raceContext: raceLabel,
        chunksUsed: totalChunks,
      };
      setMessages((prev) => [...prev, aiMsg]);
    } catch (err: any) {
      const errMsg: Message = {
        id: `${Date.now()}-e`,
        role: 'ai',
        text: err?.message ?? 'Failed to reach the PitWall RAG backend. Check that the API server is running.',
        timestamp: timeNow(),
        raceContext: raceLabel,
        isError: true,
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const totalVectorChunks = (status.laps || 0) + (status.weather || 0) + (status.pitstops || 0) + (status.radio || 0);

  return (
    <div className="flex flex-col gap-6 pb-12">
      {/* 1. Liquid Glass Circuit Selector */}
      <CircuitGlassSelector
        selectedYear={selectedYear}
        onYearChange={setSelectedYear}
        selectedRace={selectedRace}
        onSelectRace={setSelectedRace}
      />

      {/* 2. RAG Strategy Vector Store Stats Bar */}
      <div className="flex flex-wrap items-stretch gap-px bg-border-rim rounded-xl overflow-hidden rim-border">
        <div className="flex-1 min-w-[140px] flex items-center gap-2 px-4 py-3 bg-surface-container-lowest/90">
          <span className="w-2 h-2 rounded-full bg-status-go animate-pulse flex-none" />
          <div className="min-w-0">
            <div className="text-[10px] text-secondary uppercase font-telemetry-sm tracking-wide">Vector DB</div>
            <div className="text-white font-bold text-sm truncate">{status.online ? 'Online' : 'Offline'}</div>
          </div>
        </div>
        <div className="flex-1 min-w-[140px] flex items-center gap-2 px-4 py-3 bg-surface-container-lowest/90">
          <span className="material-symbols-outlined text-f1-red text-lg flex-none">database</span>
          <div className="min-w-0">
            <div className="text-[10px] text-secondary uppercase font-telemetry-sm tracking-wide">Lap Chunks</div>
            <div className="text-white font-bold text-sm truncate">{status.laps?.toLocaleString() ?? 0}</div>
          </div>
        </div>
        <div className="flex-1 min-w-[140px] flex items-center gap-2 px-4 py-3 bg-surface-container-lowest/90">
          <span className="material-symbols-outlined text-sky-400 text-lg flex-none">cloud</span>
          <div className="min-w-0">
            <div className="text-[10px] text-secondary uppercase font-telemetry-sm tracking-wide">Weather Logs</div>
            <div className="text-white font-bold text-sm truncate">{status.weather?.toLocaleString() ?? 0}</div>
          </div>
        </div>
        <div className="flex-1 min-w-[140px] flex items-center gap-2 px-4 py-3 bg-surface-container-lowest/90">
          <span className="material-symbols-outlined text-amber-400 text-lg flex-none">radio</span>
          <div className="min-w-0">
            <div className="text-[10px] text-secondary uppercase font-telemetry-sm tracking-wide">Radio Chunks</div>
            <div className="text-white font-bold text-sm truncate">{status.radio?.toLocaleString() ?? 0}</div>
          </div>
        </div>
      </div>

      {/* 3. Interactive RAG Chat Window */}
      <div className="liquid-glass rounded-2xl rim-border flex flex-col h-[75vh] min-h-[560px] max-h-[840px] overflow-hidden relative shadow-2xl">
        {/* Chat Window Top Bar */}
        <div className="px-5 sm:px-6 py-4 bg-surface-container-lowest/90 border-b border-border-rim flex justify-between items-center z-10 flex-none">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-9 h-9 rounded-xl bg-f1-red/20 border border-f1-red/40 flex items-center justify-center text-f1-red glow-red flex-none">
              <span className="material-symbols-outlined text-xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                smart_toy
              </span>
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h3 className="font-headline-md text-white text-base tracking-tight uppercase truncate">
                  PitWall RAG Assistant
                </h3>
                <span className="hidden sm:inline-flex px-2 py-0.5 rounded text-[10px] font-telemetry-sm uppercase font-bold bg-f1-red/20 text-f1-red border border-f1-red/30 flex-none">
                  Swarm Active
                </span>
              </div>
              <p className="text-[11px] text-secondary font-telemetry-sm uppercase truncate">
                Context: <span className="text-white font-bold">{raceLabel}</span>
              </p>
            </div>
          </div>

          <div className="hidden md:flex items-center gap-3 text-[11px] font-telemetry-sm text-secondary flex-none">
            <span className="flex items-center gap-1.5 bg-surface-container px-3 py-1.5 rounded-full border border-border-rim">
              <span className="w-2 h-2 rounded-full bg-status-go animate-pulse" />
              {totalVectorChunks.toLocaleString()} chunks indexed
            </span>
          </div>
        </div>

        {/* Conversation Stream */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-5 scroll-smooth">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex items-start gap-3 animate-message-in ${
                msg.role === 'user' ? 'flex-row-reverse' : ''
              }`}
            >
              {/* Avatar */}
              <div
                className={`w-8 h-8 rounded-lg flex items-center justify-center flex-none mt-0.5 ${
                  msg.role === 'ai'
                    ? 'bg-f1-red/15 border border-f1-red/30 text-f1-red'
                    : 'bg-surface-container-high border border-border-rim text-on-surface'
                }`}
              >
                <span className="material-symbols-outlined text-base">
                  {msg.role === 'ai' ? 'smart_toy' : 'engineering'}
                </span>
              </div>

              <div className={`flex flex-col min-w-0 flex-1 ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                {/* Role Header */}
                <div className="flex items-center gap-2 text-[11px] font-telemetry-sm text-secondary px-1 mb-1">
                  {msg.role === 'ai' ? (
                    <>
                      <span className="text-f1-red font-bold uppercase flex items-center gap-1">
                        <span className="material-symbols-outlined text-xs">auto_awesome</span>
                        Strategy Swarm AI
                      </span>
                      <span>•</span>
                      <span>{msg.timestamp}</span>
                      {msg.chunksUsed !== undefined && (
                        <span className="hidden xs:inline bg-surface-container-high px-2 py-0.5 rounded text-[10px] text-secondary border border-border-rim">
                          {msg.chunksUsed} chunks
                        </span>
                      )}
                    </>
                  ) : (
                    <>
                      <span className="text-white font-bold uppercase">Race Engineer</span>
                      <span>•</span>
                      <span>{msg.timestamp}</span>
                    </>
                  )}
                </div>

                {/* Message Bubble */}
                <div
                  className={`max-w-full md:max-w-[85%] p-4 sm:p-5 rounded-2xl transition-all duration-300 ${
                    msg.role === 'user'
                      ? 'bg-f1-red/20 border border-f1-red/40 text-white rounded-tr-none glow-red shadow-lg'
                      : msg.isError
                        ? 'bg-status-stop/10 border border-status-stop/40 text-on-surface rounded-tl-none shadow-xl'
                        : 'liquid-glass text-on-surface rounded-tl-none border-white/10 shadow-xl'
                  }`}
                >
                  {msg.isError && (
                    <div className="flex items-center gap-1.5 text-status-stop text-xs font-bold uppercase mb-2 font-telemetry-sm">
                      <span className="material-symbols-outlined text-sm">error</span>
                      Telemetry Error
                    </div>
                  )}

                  <div className="font-body-md text-[15px] text-white/90">
                    {msg.role === 'ai' ? <MarkdownLite text={msg.text} /> : (
                      <p className="leading-relaxed whitespace-pre-wrap">{msg.text}</p>
                    )}
                  </div>

                  {/* Source Citation Chips + Agent Breakdown */}
                  {msg.role === 'ai' && msg.agents && msg.agents.length > 0 && (
                    <div className="mt-5 pt-4 border-t border-white/10 space-y-3">
                      <div className="flex flex-wrap items-center gap-2 text-xs font-telemetry-sm">
                        <span className="text-secondary uppercase text-[10px] tracking-wide">Specialist Agents:</span>
                        {msg.agents.map((ag) => (
                          <span
                            key={ag.agent}
                            className="px-2.5 py-1 rounded-md bg-surface-container-high/80 border border-white/10 text-white text-[11px] flex items-center gap-1.5"
                          >
                            <span
                              className="w-2 h-2 rounded-full flex-none"
                              style={{ backgroundColor: AGENT_STYLE[ag.agent]?.color ?? '#e10600' }}
                            />
                            {AGENT_STYLE[ag.agent]?.name ?? ag.agent}
                          </span>
                        ))}
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                        {msg.agents.map((ag) => (
                          <AgentCard key={ag.agent} agent={ag} />
                        ))}
                      </div>
                      <p className="text-[10px] text-secondary/70 font-telemetry-sm uppercase tracking-wide">
                        Tap a card to view the full specialist analysis
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}

          {/* Animated Synthesizing Indicator */}
          {loading && (
            <div className="flex items-start gap-3 animate-message-in">
              <div className="w-8 h-8 rounded-lg bg-f1-red/15 border border-f1-red/30 text-f1-red flex items-center justify-center flex-none mt-0.5">
                <span className="material-symbols-outlined text-base">smart_toy</span>
              </div>
              <div className="p-4 rounded-2xl rounded-tl-none liquid-glass border-f1-red/30 flex items-center gap-3">
                <div className="flex items-center gap-1" aria-hidden="true">
                  <span className="w-2 h-2 rounded-full bg-f1-red dot-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-2 h-2 rounded-full bg-f1-red dot-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-2 h-2 rounded-full bg-f1-red dot-bounce" style={{ animationDelay: '300ms' }} />
                </div>
                <div>
                  <div className="font-headline-md text-white text-sm uppercase">
                    {LOADING_STAGES[loadingStage]}
                  </div>
                  <div className="font-telemetry-sm text-[11px] text-secondary">
                    This can take up to ~20 seconds for multi-agent queries
                  </div>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Quick Strategy Prompt Chips */}
        <div className="px-4 sm:px-6 py-2.5 bg-surface-container-lowest/50 border-t border-border-rim flex items-center gap-2 overflow-x-auto no-scrollbar flex-none">
          <span className="text-[11px] font-telemetry-sm text-secondary uppercase flex-none">
            Quick Prompts:
          </span>
          {SAMPLE_PROMPTS.map((promptText, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => send(promptText)}
              disabled={loading}
              className="flex-none px-3 py-1.5 rounded-full bg-surface-container-low hover:bg-surface-container-high border border-border-rim hover:border-f1-red/40 text-xs font-body-sm text-on-surface hover:text-white transition-all whitespace-nowrap active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-f1-red/60"
            >
              {promptText}
            </button>
          ))}
        </div>

        {/* RAG Query Input Bar */}
        <div className="p-4 bg-surface-container-lowest/90 border-t border-border-rim flex-none">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="relative flex items-center w-full"
          >
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={loading}
              aria-label="Ask PitWall RAG a strategy question"
              placeholder={`Ask about ${raceLabel} strategy, tyres, pit windows, radio...`}
              className="w-full bg-background-surface/90 border border-border-rim focus:border-f1-red rounded-xl font-body-md text-sm py-3.5 pl-5 pr-14 outline-none placeholder-secondary/50 text-white transition-all shadow-inner focus:outline-none focus-visible:ring-2 focus-visible:ring-f1-red/50 disabled:opacity-60"
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              aria-label="Send question"
              className="absolute right-2.5 w-9 h-9 flex items-center justify-center bg-f1-red text-white rounded-lg hover:bg-f1-red-hover transition-all duration-200 active:scale-95 shadow-md shadow-f1-red/30 disabled:opacity-40 disabled:pointer-events-none cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-white/60"
            >
              {loading ? (
                <span className="material-symbols-outlined text-base animate-spin">autorenew</span>
              ) : (
                <span className="material-symbols-outlined text-base">send</span>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
