"""
Unit tests for core.agents.base.BaseAgent.

We test the LEAF pattern:
  - LSP conformance (all agents can be used as BaseAgent)
  - dependency‑injection via the IToolExecutor/scratchpad protocol
  - and how `think`–`act`–`observe` behave under simple mocks.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from core.agents.base import BaseAgent, AgentConfig
from core.mcp.protocol import IToolExecutor, ToolCall, ToolResult
from core.scratchpad.scratchpad_manager import ScratchpadManager
from core.models.task_model import TaskPriority


class StubToolExecutor(IToolExecutor):
    """Stub implementation of IToolExecutor for testing BaseAgent."""

    async def invoke_tool(
        self,
        tool_name: str,
        arguments: dict,
    ) -> ToolResult:
        """Echo the call and always succeed."""
        return ToolResult(
            success=True,
            content=f"invoked {tool_name} with {arguments!r}",
            metadata={"tool_name": tool_name, "arguments": arguments},
        )


class UnstableToolExecutor(IToolExecutor):
    """Tool executor that sometimes fails."""

    def __init__(self, fail_every: int = 2) -> None:
        self.call_count = 0
        self.fail_every = fail_every

    async def invoke_tool(
        self,
        tool_name: str,
        arguments: dict,
    ) -> ToolResult:
        self.call_count += 1
        if self.call_count % self.fail_every == 0:
            return ToolResult(
                success=False,
                error=f"artificial error at call {self.call_count}",
                metadata={"tool_name": tool_name},
            )
        return ToolResult(
            success=True,
            content="ok",
            metadata={"tool_name": tool_name, "call_count": self.call_count},
        )


class TestBaseAgent:
    """Unit tests for BaseAgent's protocol and base behavior."""

    @pytest.fixture
    def config(self) -> AgentConfig:
        return AgentConfig()

    @pytest.fixture
    def mock_scratchpad(self) -> MagicMock:
        m = MagicMock(spec=ScratchpadManager)
        m.append_section = AsyncMock()
        m.append_error = AsyncMock()
        return m

    @pytest.fixture
    def agent(self, mock_scratchpad: MagicMock) -> BaseAgent:
        tools = StubToolExecutor()
        return BaseAgent(
            agent_id="test-agent",
            project_id="test-project",
            tools=tools,
            scratchpad=mock_scratchpad,
            config=AgentConfig(),
        )

    def test_initialization(self, agent: BaseAgent) -> None:
        """BaseAgent initializes with the expected attributes."""
        assert agent.agent_id == "test-agent"
        assert agent.project_id == "test-project"
        assert isinstance(agent.config, AgentConfig)
        assert agent.tools is not None
        assert agent.scratchpad is not None

    def test_think_produces_context_dict(self, agent: BaseAgent) -> None:
        """BaseAgent.think always returns a dict that can be fed into act."""
        plan = agent.think(
            "write a simple hello world module",
            {"task_id": "test-task"},
        )
        assert isinstance(plan, dict)
        assert "task_description" in plan
        assert "context" in plan
        assert "agent_id" in plan
        assert "project_id" in plan

    def test_act_returns_tool_call(self, agent: BaseAgent) -> None:
        """BaseAgent.act always returns a ToolCall shaped as per MCP."""
        plan = agent.think(
            "write a simple hello world module",
            {"task_id": "test-task"},
        )
        context = {
            "task_id": "test-task",
            "iteration": 0,
        }
        tool_call = agent.act(plan, context)
        assert isinstance(tool_call, ToolCall)
        assert tool_call.tool_name == "llm.invoke_tool"
        # note: BaseAgent's default act is a stub; real agents override this

    async def test_observe_records_success(self, agent: BaseAgent) -> None:
        """BaseAgent.observe records success to the scratchpad when enabled."""
        context = {
            "task_id": "test-task",
        }
        result = ToolResult(
            success=True,
            content="all tests passed",
            metadata={"path": "src/main.py"},
        )

        agent.config.scratchpad_enabled = True
        new_context = await agent.observe(result, context)
        agent.scratchpad.append_section.assert_awaited_once()
        # preserve context keys
        assert new_context["status"] == "completed"
        assert "last_result" in new_context

    async def test_observe_records_failure(self, agent: BaseAgent) -> None:
        """BaseAgent.observe records errors and updates status when failed."""
        context = {"task_id": "test-task"}
        result = ToolResult(
            success=False,
            error="test command failed",
            metadata={"tool_name": "test_runner"},
        )

        agent.config.scratchpad_enabled = True
        new_context = await agent.observe(result, context)
        agent.scratchpad.append_error.assert_awaited_once()
        assert new_context["status"] == "failed"
        assert "last_error" in new_context
        assert "test_runner" in new_context["last_error"]

    async def test_think_with_scratchpad(self, agent: BaseAgent) -> None:
        """BaseAgent writes a plan section when scratchpad is enabled."""
        agent.config.scratchpad_enabled = True
        agent.config.model_id = "test-model"
        context = {"task_id": "test-task"}

        plan = agent.think("refactor X", context)
        agent.scratchpad.append_section.assert_awaited_once_with(
            project_id="test-project",
            agent_id="test-agent",
            task_id="test-task",
            section="Plan",
            content=plan,
        )
        # task_priority is just passed through the base impl
        assert plan.get("task_priority") == TaskPriority.NORMAL.value

    async def test_observe_with_disabled_scratchpad(self, agent: BaseAgent) -> None:
        """BaseAgent does not write to scratchpad when disabled."""
        context = {"task_id": "test-task"}
        result = ToolResult(
            success=True,
            content="ok",
        )

        agent.config.scratchpad_enabled = False
        new_context = await agent.observe(result, context)
        agent.scratchpad.append_section.assert_not_called()
        agent.scratchpad.append_error.assert_not_called()
        assert new_context.get("status") == "completed"
