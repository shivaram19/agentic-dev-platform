# core/langgraph package
"""
Agentic Development Platform - LangGraph Layer

Top‑level module exposing the agent graph implementation that orchestrates
cycles of THINK‑ACT‑OBSERVE across multiple specialized agents.

This layer treats the agent graph as a DAG of callable nodes, compatible
with typical “langgraph”‑style libraries and tooling.[web:244]
"""

from core.langgraph.agent_graph import AgentGraph, AgentState
from core.langgraph.runner import run_agent_graph

__all__ = [
    "AgentGraph",
    "AgentState",
    "run_agent_graph",
]
