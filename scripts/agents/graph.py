"""LangGraph orchestration for the Bull vs Bear debate.

State machine:

    bull_opening  →  bear_opening  →  bull_rebuttal  →  bear_rebuttal
                                          ↑                  │
                                          └── (round < max) ─┘
                                                             │
                                                          (max)
                                                             ↓
                                                       facilitator
                                                             ↓
                                                            END

Each node returns a partial state update; the `bull_rounds` /
`bear_rounds` reducers append (operator.add concatenates lists).
The conditional edge after `bear_rebuttal` controls how many rebuttal
cycles run before the facilitator is invoked.

Public surface:
    DebateState     — TypedDict for the graph state
    build_debate_graph()  — compiled LangGraph
    run_debate(ticker_data, max_rounds=2) — convenience wrapper that
        returns a flat dict with the verdict + transcripts
"""

from __future__ import annotations

import operator
import sys
from pathlib import Path
from typing import Annotated, Any, TypedDict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from langgraph.graph import END, StateGraph  # noqa: E402

from scripts.agents.bear_researcher import (  # noqa: E402
    bear_initial_argument,
    bear_rebuttal,
)
from scripts.agents.bull_researcher import (  # noqa: E402
    bull_initial_argument,
    bull_rebuttal,
)
from scripts.agents.debate_facilitator import facilitate_debate  # noqa: E402


class DebateState(TypedDict, total=False):
    ticker_data: dict[str, Any]
    bull_rounds: Annotated[list[str], operator.add]
    bear_rounds: Annotated[list[str], operator.add]
    current_round: int
    max_rounds: int
    verdict: dict[str, Any]


# ---------------------------------------------------------------------------
# Nodes (each takes the full state, returns the partial update)
# ---------------------------------------------------------------------------
def bull_opening_node(state: DebateState) -> dict[str, Any]:
    arg = bull_initial_argument(state["ticker_data"])
    return {
        "bull_rounds": [arg or "(Bull opening unavailable — LLM client missing or API error)"],
        "current_round": 1,
    }


def bear_opening_node(state: DebateState) -> dict[str, Any]:
    arg = bear_initial_argument(state["ticker_data"])
    return {
        "bear_rounds": [arg or "(Bear opening unavailable — LLM client missing or API error)"],
    }


def bull_rebuttal_node(state: DebateState) -> dict[str, Any]:
    last_bear = state["bear_rounds"][-1] if state.get("bear_rounds") else ""
    arg = bull_rebuttal(last_bear, conversation_history=None)
    return {
        "bull_rounds": [arg or "(Bull rebuttal unavailable)"],
    }


def bear_rebuttal_node(state: DebateState) -> dict[str, Any]:
    last_bull = state["bull_rounds"][-1] if state.get("bull_rounds") else ""
    arg = bear_rebuttal(last_bull, conversation_history=None)
    return {
        "bear_rounds": [arg or "(Bear rebuttal unavailable)"],
        "current_round": int(state.get("current_round", 1)) + 1,
    }


def facilitator_node(state: DebateState) -> dict[str, Any]:
    verdict = facilitate_debate(
        state["ticker_data"],
        state.get("bull_rounds") or [],
        state.get("bear_rounds") or [],
    )
    if verdict is None:
        verdict = {
            "verdict": "thesis_neutral",
            "weight": "balanced",
            "suggested_action": "maintain",
            "confidence": "low",
            "reasoning": "Facilitator LLM unavailable; defaulted to neutral.",
            "_facilitator_failed": True,
        }
    return {"verdict": verdict}


# ---------------------------------------------------------------------------
# Conditional routing
# ---------------------------------------------------------------------------
def should_continue(state: DebateState) -> str:
    """Loop until `current_round` reaches `max_rounds`. After the bear
    rebuttal increments the round counter, decide whether to spin
    another rebuttal cycle or hand off to the facilitator."""
    if int(state.get("current_round", 0)) >= int(state.get("max_rounds", 1)):
        return "facilitator"
    return "bull_rebuttal"


# ---------------------------------------------------------------------------
# Graph build + entry point
# ---------------------------------------------------------------------------
def build_debate_graph():
    workflow = StateGraph(DebateState)

    workflow.add_node("bull_opening", bull_opening_node)
    workflow.add_node("bear_opening", bear_opening_node)
    workflow.add_node("bull_rebuttal", bull_rebuttal_node)
    workflow.add_node("bear_rebuttal", bear_rebuttal_node)
    workflow.add_node("facilitator", facilitator_node)

    workflow.set_entry_point("bull_opening")
    workflow.add_edge("bull_opening", "bear_opening")
    workflow.add_edge("bear_opening", "bull_rebuttal")
    workflow.add_edge("bull_rebuttal", "bear_rebuttal")
    workflow.add_conditional_edges(
        "bear_rebuttal",
        should_continue,
        {"bull_rebuttal": "bull_rebuttal", "facilitator": "facilitator"},
    )
    workflow.add_edge("facilitator", END)

    return workflow.compile()


def run_debate(
    ticker_data: dict[str, Any], max_rounds: int = 2
) -> dict[str, Any]:
    """Run the full Bull vs Bear debate end-to-end.

    Returns a flat dict containing the verdict fields PLUS the
    transcripts (`bull_rounds`, `bear_rounds`). When the facilitator
    fails the verdict still carries default values so persistence
    code never sees a missing key."""
    graph = build_debate_graph()
    initial_state: DebateState = {
        "ticker_data": ticker_data,
        "bull_rounds": [],
        "bear_rounds": [],
        "current_round": 0,
        "max_rounds": max_rounds,
        "verdict": {},
    }
    final_state = graph.invoke(initial_state)
    verdict = final_state.get("verdict") or {}
    return {
        **verdict,
        "bull_rounds": final_state.get("bull_rounds", []) or [],
        "bear_rounds": final_state.get("bear_rounds", []) or [],
    }
