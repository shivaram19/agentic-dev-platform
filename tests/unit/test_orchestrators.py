"""
Unit tests for orchestrator‑style agents (e.g., OrchestratorAgent).

These tests focus on:
  - task decomposition and sub‑plan creation,
  - how the orchestrator routes to different agents/tools,
  - and how it updates high‑level state based on agent results.

We use stubs for the agents and tools to keep the tests fast and deterministic.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from core.agents.base import BaseAgent, AgentConfig
from core.mcp.protocol import IToolExecutor, ToolCall, ToolResult
from core.scratchpad.scratchpad_manager import ScratchpadManager
from core.llm.llm_client import LLMClient
from core.orchestrator.orchestrator_agent import OrchestratorAgent


class MockLLMClient(LLMClient):
    """Stub LLMClient that returns fixed responses."""

    async def generate_text(
        self,
        system: str,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> str:
        if "subtask" in prompt.lower():
            return """
{
  "subtasks": [
    {"id": "1", "task": "Extract requirements from user request", "agent": "coder"},
    {"id": "2", "task": "Generate code module", "agent": "coder"},
    {"id": "3", "task": "Add unit tests", "agent": "test-writer"},
    {"id": "4", "task": "Refactor", "agent": "refactor-agent"}
  ]
}
"""
        if "plan" in prompt.lower():
            return """
{
  "task_description": "Write a Python module and add tests",
  "subtasks": [
    {"id": "1", "task": "Sketch requirements", "agent": "coder"},
    {"id": "2", "task": "Implement code", "agent": "coder"},
    {"id": "3", "task": "Add tests", "agent": "test-agent"}
  ]
}
"""
        return '{"subtasks": []}'


class StubAgent(BaseAgent):
    """Stub agent that produces a hard‑coded plan."""

    def think(self, task_description: str, context: dict) -> dict:
        return {
            "task_description": task_description,
            "subtasks": [],
            "agent_id": self.agent_id,
            "project_id": self.project_id,
        }

    def act(self, plan: dict, context: dict) -> ToolCall:
        return ToolCall(
            id=f"{self.agent_id}-{context['task_id']}-{context['iteration']}",
            tool_name="test_agent.act",
            arguments={"plan": plan},
        )

    async def observe(self, tool_result: ToolResult, context: dict) -> dict:
        context["status"] = "completed"
        return context


class TestOrchestratorAgent:
    """Unit tests for OrchestratorAgent."""

    @pytest.fixture
    def config(self) -> AgentConfig:
        return AgentConfig()

    @pytest.fixture
    def tools(self) -> IToolExecutor:
        return MagicMock(spec=IToolExecutor)

    @pytest.fixture
    def llm_client(self) -> MockLLMClient:
        return MockLLMClient()

    @pytest.fixture
    def scratchpad(self) -> MagicMock:
        m = MagicMock(spec=ScratchpadManager)
        m.append_section = AsyncMock()
        m.append_error = AsyncMock()
        return m

    @pytest.fixture
    def orchestrator(
        self,
        tools: IToolExecutor,
        scratchpad: MagicMock,
        llm_client: MockLLMClient,
    ) -> OrchestratorAgent:
        return OrchestratorAgent(
            agent_id="orchestrator-test",
            project_id="test-project",
            tools=tools,
            scratchpad=scratchpad,
            llm_client=llm_client,
            config=AgentConfig(),
        )

    def test_initialization(
        self, orchestrator: OrchestratorAgent
    ) -> None:
        assert orchestrator.agent_id == "orchestrator-test"
        assert orchestrator.project_id == "test-project"
        assert orchestrator.tools is not None
        assert orchestrator.scratchpad is not None
        assert orchestrator.llm_client is not None

    async def test_think_decomposes_simple_task(
        self, orchestrator: OrchestratorAgent
    ) -> None:
        """Orchestrator decomposes a simple task into a subtask list."""
        plan = await orchestrator.think(
            task_description="Write a Python module with tests",
            context={"task_id": "test-task"},
        )
        assert isinstance(plan, dict)
        assert "task_description" in plan
        assert "subtasks" in plan
        assert len(plan["subtasks"]) > 0
        first = plan["subtasks"][0]
        assert isinstance(first, dict)
        assert "id" in first
        assert "task" in first
        assert "agent" in first

    async def test_think_with_scratchpad(
        self, orchestrator: OrchestratorAgent
    ) -> None:
        """Orchestrator records the decomposition in the scratchpad."""
        context = {"task_id": "test-task"}
        orchestrator.config.scratchpad_enabled = True

        plan = await orchestrator.think(
            task_description="Refactor X",
            context=context,
        )
        orchestrator.scratchpad.append_section.assert_awaited_once_with(
            project_id="test-project",
            agent_id="orchestrator-test",
            task_id="test-task",
            section="Plan",
            content=plan,
        )

    async def test_act_routes_subtasks_to_correct_agents(
        self, orchestrator: OrchestratorAgent
    ) -> None:
        """Orchestrator.act routes each subtask to the designated agent."""
        plan = await orchestrator.think(
            task_description="Implement and test a module",
            context={"task_id": "test-task"},
        )
        context = {
            "task_id": "test-task",
            "iteration": 0,
            "current_subtask_idx": 0,
        }

        # In this stub the orchestrator is only a routing layer;
        # real agents are replaced by a stub.
        # For a full implementation you would pass a registry of agents here.
        # For unit tests we just verify that it produces a subtask‑specific ToolCall.
        tool_call = await orchestrator.act(plan, context)
        assert isinstance(tool_call, ToolCall)
        assert tool_call.tool_name == "orchestrator.route_subtask"
        assert "subtask" in tool_call.arguments
        assert "agent_id" in tool_call.arguments["subtask"]

    async def test_observe_aggregates_subtask_results(
        self, orchestrator: OrchestratorAgent
    ) -> None:
        """Orchestrator.observe aggregates subtask results and updates status."""
        context = {"task_id": "test-task", "subtasks": [{"id": "1", "status": "running"}]}
        result = ToolResult(
            success=True,
            content="subtask 1 completed",
            metadata={"subtask_id": "1"},
        )
        orchestrator.config.scratchpad_enabled = True

        new_context = await orchestrator.observe(result, context)
        assert new_context.get("status") == "completed"
        assert new_context.get("subtasks") == [
            {"id": "1", "status": "completed", "result": "subtask 1 completed"}
        ]
        orchestrator.scratchpad.append_section.assert_awaited()

    async def test_observe_propagates_failure(
        self, orchestrator: OrchestratorAgent
    ) -> None:
        """Orchestrator.observe updates status to failed if a subtask fails."""
        context = {"task_id": "test-task", "subtasks": [{"id": "1", "status": "running"}]}
        result = ToolResult(
            success=False,
            error="subtask failed",
            metadata={"subtask_id": "1"},
        )
        orchestrator.config.scratchpad_enabled = True
        new_context = await orchestrator.observe(result, context)
        assert new_context.get("status") == "failed"
        assert "last_error" in new_context
        assert "subtask failed" in new_context["last_error"]
