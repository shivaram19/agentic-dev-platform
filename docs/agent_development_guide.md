# Agent Development Guide

This guide explains how to build and extend agents within the Agentic Development Platform. It assumes familiarity with the core `BaseAgent` and the Think–Act–Observe (T‑A‑O) pattern.

## Prerequisites

- Basic Python knowledge (async/await, typing, dependency injection).
- Understanding of `core.agents.base.BaseAgent` and `core.mcp.protocol` (tool calls and results).
- Access to `tests/unit/test_base_agent.py` and `tests/unit/test_orchestrators.py` as reference tests.

## Agent Design Philosophy

- **Single responsibility**: each agent type owns a narrow domain (code, tests, docs, voice, etc.).
- **Composability**: agents can be chained via an `OrchestratorAgent` or via scratchpad‑based coordination.
- **Dependency‑inversion**: agents depend only on tool *contracts* (`IToolExecutor`) and the scratchpad, not on concrete MCP implementations.

## Step 1: Define a New Agent Class

Follow the pattern in `core.agents.code_agent.CodeAgent`:

1. Create `core/agents/your_agent.py`.
2. Subclass `BaseAgent` and add any agent‑specific config.
3. Implement `think`, `act`, and `observe` such that:

   - `think` converts a task description and context into a plan dictionary.
   - `act` uses that plan to produce a `ToolCall`.
   - `observe` consumes the `ToolResult` and updates the context.

Example skeleton:

```python
from core.agents.base import BaseAgent, AgentConfig
from core.mcp.protocol import ToolCall, ToolResult
from typing import Dict, Any

@dataclass(frozen=True)
class YourAgentConfig(AgentConfig):
    custom_param: str = "default"

class YourAgent(BaseAgent):
    def __init__(..., config: YourAgentConfig):
        super().__init__(..., config=config)
        self._config = config  # Narrowed type

    def think(self, task_description: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # ...
        return plan

    def act(self, plan: Dict[str, Any], context: Dict[str, Any]) -> ToolCall:
        # ...
        return tool_call

    async def observe(self, tool_result: ToolResult, context: Dict[str, Any]) -> Dict[str, Any]:
        # ...
        return context
```

## Step 2: Leverage the Scratchpad

If `config.scratchpad_enabled` is `True`, record:

- Plans in a `"Plan"` section.
- Observations and errors in `"Observations"` or `"Errors"`.

Example:

```python
if self.config.scratchpad_enabled:
    await self.scratchpad.append_section(
        project_id=self.project_id,
        agent_id=self.agent_id,
        task_id=context["task_id"],
        section="Plan",
        content=plan,
    )
```

## Step 3: Use Tool Contracts, Not Implementations

Do not call MCP server internals directly. Instead:

- Accept an `IToolExecutor` in `__init__`.
- Produce `ToolCall` objects in `act`.
- Interpret `ToolResult` metadata and content in `observe`.

This allows the same agent to run against different MCP backends (local, remote, mocked).

## Step 4: Testing Your Agent

- **Unit tests**: `tests/unit/test_your_agent.py`.
- Verify that `think` returns a well‑shaped plan, `act` produces valid `ToolCall`s, and `observe` correctly updates context.
- Use `StubToolExecutor` and `UnstableToolExecutor` from `tests/unit/test_base_agent.py` as test doubles.
- Assert scratchpad interactions when `scratchpad_enabled` is enabled.

## Step 5: Integrating with the Orchestrator

If your agent participates in multi‑step workflows:

- Add it to an agent registry (or configuration) that the `OrchestratorAgent` can route to.
- Ensure its `think` returns plans that include `"agent_id"` hints.
- The orchestrator’s `act` can then conditionally route subtasks to your agent based on that field.

## Recommended Patterns

- **Immutable configuration**: use `@dataclass(frozen=True)` for agent config.
- **Idempotent tools**: prefer tools that describe what to do (e.g., patches) rather than imperative mutations.
- **Auditable history**: log all plans and results to the scratchpad so that failures can be replayed.

## Things to Avoid

- Coupling to a specific LLM backend or MCP transport.
- Directly writing to project files without going through approved tools.
- Storing large artifacts inside the agent; instead store references or IDs in the scratchpad.

With this guide, you can extend the platform with new agents such as:

- Test‑generation agents.
- Documentation‑generation agents.
- Dependency‑management or security‑linting agents.
