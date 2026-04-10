"""
Agentic Development Platform - LangGraph Agent Graph Runner.

Wraps the LangGraph StateGraph workflow so that orchestrators and agents
interact only with this class — never with LangGraph internals directly.

SRP : Manages ONLY the state-machine lifecycle for one agent TAO loop.
DIP : Orchestrators depend on AgentGraphRunner, not on LangGraph types.
OCP : New states/edges are added by subclassing or config, not by editing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Callable, Awaitable
import asyncio
import structlog

log = structlog.get_logger(__name__)


# ── State Definitions ─────────────────────────────────────────────────────────

class AgentState(str, Enum):
    """All possible states in the T-A-O agent state machine."""
    INIT       = "INIT"
    THINKING   = "THINKING"
    ACTING     = "ACTING"
    OBSERVING  = "OBSERVING"
    COMPLETED  = "COMPLETED"
    FAILED     = "FAILED"


@dataclass
class GraphContext:
    """
    Mutable context object passed through every state transition.

    This is the 'state' node in the LangGraph StateGraph.
    All agents read from and write to this object during execution.
    """
    task_id:     str
    project_id:  str
    agent_id:    str
    description: str
    parameters:  Dict[str, Any]          = field(default_factory=dict)
    iteration:   int                     = 0
    max_iter:    int                     = 10
    status:      AgentState              = AgentState.INIT
    last_result: Optional[str]           = None
    last_error:  Optional[str]           = None
    metadata:    Dict[str, Any]          = field(default_factory=dict)


# ── Type aliases ──────────────────────────────────────────────────────────────

ThinkFn  = Callable[[str, Dict[str, Any]], Awaitable[Dict[str, Any]]]
ActFn    = Callable[[Dict[str, Any], Dict[str, Any]], Awaitable[Any]]
ObserveFn = Callable[[Any, Dict[str, Any]], Awaitable[Dict[str, Any]]]


# ── Runner ────────────────────────────────────────────────────────────────────

class AgentGraphRunner:
    """
    Executes the Think → Act → Observe state machine for one agent session.

    This class is intentionally framework-agnostic in its public interface.
    Internally it can be backed by LangGraph, a simple loop, or any other
    state machine — callers never need to know.

    Usage:
        runner = AgentGraphRunner(
            context=GraphContext(...),
            think_fn=agent.think,
            act_fn=agent.act,
            observe_fn=agent.observe,
        )
        final_ctx = await runner.run()
    """

    def __init__(
        self,
        context: GraphContext,
        think_fn:   ThinkFn,
        act_fn:     ActFn,
        observe_fn: ObserveFn,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        """
        Args:
            context:              Shared mutable context for this run.
            think_fn:             Bound method → agent.think().
            act_fn:               Bound method → agent.act().
            observe_fn:           Bound method → agent.observe().
            retry_delay_seconds:  Base delay between retries (exponential).
        """
        self._ctx                 = context
        self._think_fn            = think_fn
        self._act_fn              = act_fn
        self._observe_fn          = observe_fn
        self._retry_delay         = retry_delay_seconds
        self._logger              = log.bind(
            task_id=context.task_id,
            agent_id=context.agent_id,
            project_id=context.project_id,
        )

    # ── Public API ────────────────────────────────────────────────────────

    async def run(self) -> GraphContext:
        """
        Execute the full T-A-O loop until COMPLETED or FAILED.

        Returns:
            Final GraphContext with status set to COMPLETED or FAILED.
        """
        self._logger.info("AgentGraphRunner.start", max_iter=self._ctx.max_iter)
        self._ctx.status = AgentState.THINKING

        while self._ctx.iteration < self._ctx.max_iter:
            self._ctx.iteration += 1
            self._logger.info(
                "AgentGraphRunner.iteration",
                iteration=self._ctx.iteration,
                state=self._ctx.status,
            )

            try:
                await self._step_think()
                await self._step_act()
                await self._step_observe()
            except Exception as exc:
                await self._handle_failure(exc)
                break

            if self._ctx.status == AgentState.COMPLETED:
                break

            if self._ctx.status == AgentState.FAILED:
                break

            # Transition back to THINKING for next iteration
            self._ctx.status = AgentState.THINKING

        else:
            # Exhausted iterations without completing
            self._ctx.status = AgentState.FAILED
            self._ctx.last_error = (
                f"Agent exceeded maximum iterations ({self._ctx.max_iter})."
            )
            self._logger.warning(
                "AgentGraphRunner.max_iter_exceeded",
                max_iter=self._ctx.max_iter,
            )

        self._logger.info(
            "AgentGraphRunner.finished",
            final_status=self._ctx.status,
            iterations=self._ctx.iteration,
        )
        return self._ctx

    # ── State steps ───────────────────────────────────────────────────────

    async def _step_think(self) -> None:
        """Execute the THINK phase and store the plan in metadata."""
        self._ctx.status = AgentState.THINKING
        ctx_dict = self._ctx_as_dict()
        plan = await self._think_fn(self._ctx.description, ctx_dict)
        self._ctx.metadata["plan"] = plan
        self._logger.debug("AgentGraphRunner.think_done", plan_keys=list(plan.keys()))

    async def _step_act(self) -> None:
        """Execute the ACT phase and store the tool call in metadata."""
        self._ctx.status = AgentState.ACTING
        plan     = self._ctx.metadata.get("plan", {})
        ctx_dict = self._ctx_as_dict()
        tool_call = await self._act_fn(plan, ctx_dict)
        self._ctx.metadata["tool_call"] = tool_call
        self._logger.debug("AgentGraphRunner.act_done")

    async def _step_observe(self) -> None:
        """Execute the OBSERVE phase and update context from result."""
        self._ctx.status = AgentState.OBSERVING
        tool_result = self._ctx.metadata.get("tool_call")
        ctx_dict    = self._ctx_as_dict()
        updated_ctx = await self._observe_fn(tool_result, ctx_dict)

        # Sync back status from returned dict
        new_status = updated_ctx.get("status", "completed")
        if new_status == "completed":
            self._ctx.status     = AgentState.COMPLETED
            self._ctx.last_result = updated_ctx.get("last_result")
        elif new_status == "failed":
            self._ctx.status     = AgentState.FAILED
            self._ctx.last_error = updated_ctx.get("last_error")

        self._logger.debug("AgentGraphRunner.observe_done", status=self._ctx.status)

    async def _handle_failure(self, exc: Exception) -> None:
        """Centralized failure handler with exponential backoff."""
        delay = self._retry_delay * (2 ** (self._ctx.iteration - 1))
        self._logger.warning(
            "AgentGraphRunner.step_failed",
            error=str(exc),
            retry_delay=delay,
            iteration=self._ctx.iteration,
        )
        self._ctx.last_error = str(exc)

        if self._ctx.iteration >= self._ctx.max_iter:
            self._ctx.status = AgentState.FAILED
        else:
            await asyncio.sleep(min(delay, 30.0))
            self._ctx.status = AgentState.THINKING

    # ── Helpers ───────────────────────────────────────────────────────────

    def _ctx_as_dict(self) -> Dict[str, Any]:
        """Serialize GraphContext to a plain dict for agent methods."""
        return {
            "task_id":     self._ctx.task_id,
            "project_id":  self._ctx.project_id,
            "agent_id":    self._ctx.agent_id,
            "description": self._ctx.description,
            "parameters":  self._ctx.parameters,
            "iteration":   self._ctx.iteration,
            "status":      self._ctx.status.value,
            "last_result": self._ctx.last_result,
            "last_error":  self._ctx.last_error,
            "metadata":    self._ctx.metadata,
        }