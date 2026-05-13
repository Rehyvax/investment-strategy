"""Multi-agent debate + reflection package (Fase 3D+3E).

Modules:
    bull_researcher       — steelmans bullish thesis
    bear_researcher       — red-teams thesis
    debate_facilitator    — synthesizes debate into structured verdict
    graph                 — LangGraph orchestration of the debate
    debate_trigger        — smart scheduling (weekly + news_high + force)
    risk_manager          — second-opinion check against concentration caps
    reflection            — realized-vs-predicted return + Brier scoring

The agents share a single Anthropic client borrowed from
`scripts.llm_narratives.get_client()` so that key management, model
selection (`MODEL`), and degraded-mode (no API key) behavior are
consistent with the rest of the system.
"""
