"""
Integration tests for cross‑project features in the agentic platform.

These tests verify that:
  - the project registry can list multiple projects,
  - tasks can be correctly routed to agents in different projects,
  - and the scratchpad safely isolates per‑project context.
"""
import asyncio
import pytest
from typing import Dict, Any
from pathlib import Path

from core.registry.project_registry import InMemoryProjectRegistry, ProjectMetadata
from core.agents.base import BaseAgent, AgentConfig
from core.mcp.protocol import IToolExecutor, ToolCall, ToolResult
from core.scratchpad.scratchpad_manager import ScratchpadManager
from core.orchestrator.orchestrator_agent import OrchestratorAgent
from core.agents.code_agent import CodeAgent
from tests.unit.test_base_agent import StubToolExecutor


@pytest.mark.asyncio
class TestCrossProjectIntegration:
    """Integration tests across multiple projects."""

    @pytest.fixture(autouse=True)
    def setup_dirs(self, tmp_path: Path) -> None:
        self.base_root = tmp_path / "projects"
        self.base_root.mkdir()

    @pytest.fixture
    def registry(self) -> InMemoryProjectRegistry:
        return InMemoryProjectRegistry()

    @pytest.fixture
    def tools(self) -> IToolExecutor:
        return StubToolExecutor()

    @pytest.fixture
    def scratchpad(self) -> ScratchpadManager:
        # Use a filesystem‑backed scratchpad under the temp root.
        return ScratchpadManager(
            base_dir=str(self.base_root.parent / "scratchpads")
        )

    @pytest.fixture
    def project_configs(self, registry: InMemoryProjectRegistry) -> Dict[str, ProjectMetadata]:
        """
        Register two test projects with different tags and default agents.
        """
        proj1_id = "project-one"
        proj1_dir = self.base_root / proj1_id
        proj1_dir.mkdir()
        proj1 = ProjectMetadata(
            project_id=proj1_id,
            root_path=proj1_dir,
            default_agent_id="code-agent",
            tags={"stack": "python", "owner": "team-a"},
        )
        registry.register(proj1)

        proj2_id = "project-two"
        proj2_dir = self.base_root / proj2_id
        proj2_dir.mkdir()
        proj2 = ProjectMetadata(
            project_id=proj2_id,
            root_path=proj2_dir,
            default_agent_id="voice-code-agent",
            tags={"stack": "javascript", "owner": "team-b"},
        )
        registry.register(proj2)

        return {"p1": proj1, "p2": proj2}

    @pytest.fixture
    def agents(
        self,
        project_configs: Dict[str, ProjectMetadata],
        tools: IToolExecutor,
        scratchpad: ScratchpadManager,
    ) -> Dict[str, BaseAgent]:
        """
        Build a test agent stack: one orchestrator and one code agent per project.
        """
        # We'll reuse the same orchestrator across projects for this test.
        orchestrator = OrchestratorAgent(
            agent_id="integration-orchestrator",
            project_id="unknown",
            tools=tools,
            scratchpad=scratchpad,
            config=AgentConfig(),
        )

        code_agent1 = CodeAgent(
            agent_id="code-agent",
            project_id=project_configs["p1"].project_id,
            tools=tools,
            scratchpad=scratchpad,
            config=AgentConfig(),
        )

        code_agent2 = CodeAgent(
            agent_id="voice-code-agent",
            project_id=project_configs["p2"].project_id,
            tools=tools,
            scratchpad=scratchpad,
            config=AgentConfig(),
        )

        return {
            "orchestrator": orchestrator,
            "p1.code": code_agent1,
            "p2.code": code_agent2,
        }

    async def test_two_projects_can_be_registered(
        self, registry: InMemoryProjectRegistry, project_configs: Dict[str, ProjectMetadata]
    ) -> None:
        """Both projects show up in the registry."""
        all_ids = sorted(registry.get_project_ids())
        expected = sorted(["project-one", "project-two"])
        assert all_ids == expected

        # Retrieve one project and check its metadata.
        meta = registry.get_project_metadata("project-one")
        assert meta is not None
        assert meta.project_id == "project-one"
        assert "team-a" in meta.tags["owner"]

    async def test_orchestrator_thinks_per_project(
        self,
        agents: Dict[str, BaseAgent],
        project_configs: Dict[str, ProjectMetadata],
    ) -> None:
        """Orchestrator produces a plan tailored to each project."""
        orchestrator = agents["orchestrator"]

        ctx1 = {
            "task_id": "p1-t1",
            "project_id": "project-one",
        }
        plan1 = await orchestrator.think(
            "create a new Python module in project‑one",
            ctx1,
        )
        assert plan1.get("project_id") == "project-one"

        ctx2 = {
            "task_id": "p2-t1",
            "project_id": "project-two",
        }
        plan2 = await orchestrator.think(
            "refactor the main module in project‑two",
            ctx2,
        )
        assert plan2.get("project_id") == "project‑two"

        # Two plans are distinct.
        assert plan1 != plan2

    async def test_code_agent_acts_per_project(
        self,
        agents: Dict[str, BaseAgent],
        project_configs: Dict[str, ProjectMetadata],
    ) -> None:
        """Each code agent routes tool calls to its own project directory."""
        code1 = agents["p1.code"]
        code2 = agents["p2.code"]

        ctx1 = {
            "task_id": "p1-run",
            "project_id": "project-one",
            "iteration": 0,
        }
        plan1 = {"target_path": "src/main.py", "change_type": "generate"}
        tool_call1 = code1.act(plan1, ctx1)
        assert isinstance(tool_call1, ToolCall)
        assert "src/main.py" in tool_call1.arguments.get("path", "")
        # The agent is still bound to project‑one.
        assert code1.project_id == "project-one"

        ctx2 = {
            "task_id": "p2-run",
            "project_id": "project-two",
            "iteration": 0,
        }
        plan2 = {"target_path": "src/main.js", "change_type": "refactor"}
        tool_call2 = code2.act(plan2, ctx2)
        assert isinstance(tool_call2, ToolCall)
        assert "src/main.js" in tool_call2.arguments.get("path", "")
        assert code2.project_id == "project‑two"

    async def test_scratchpad_isolates_projects(
        self,
        scratchpad: ScratchpadManager,
        project_configs: Dict[str, ProjectMetadata],
    ) -> None:
        """Scratchpad entries are separated by project_id and agent_id."""
        proj1_id = "project-one"
        proj2_id = "project-two"

        await scratchpad.append_section(
            project_id=proj1_id,
            agent_id="code-agent",
            task_id="t1",
            section="Plan",
            content="project one plan",
        )
        await scratchpad.append_section(
            project_id=proj2_id,
            agent_id="code-agent",
            task_id="t2",
            section="Plan",
            content="project two plan",
        )

        # Read project‑one's plan
        lines1 = []
        async for line in scratchpad.read_section(
            project_id=proj1_id,
            agent_id="code-agent",
            task_id="t1",
            section="Plan",
        ):
            lines1.append(line)

        assert "project one plan" in "\n".join(lines1)
        assert "project two plan" not in "\n".join(lines1)

        # Read project‑two's plan
        lines2 = []
        async for line in scratchpad.read_section(
            project_id=proj2_id,
            agent_id="code-agent",
            task_id="t2",
            section="Plan",
        ):
            lines2.append(line)

        assert "project two plan" in "\n".join(lines2)
        assert "project one plan" not in "\n".join(lines2)

    async def test_cross_project_task_flow(
        self,
        registry: InMemoryProjectRegistry,
        agents: Dict[str, BaseAgent],
        project_configs: Dict[str, ProjectMetadata],
    ) -> None:
        """
        Run a full think–act–observe loop for two projects and assert that
        state is not leaked between them.
        """
        orchestrator = agents["orchestrator"]
        code1 = agents["p1.code"]
        code2 = agents["p2.code"]

        # Task 1: project‑one
        ctx1 = {
            "task_id": "p1.cross-task-1",
            "project_id": "project-one",
            "iteration": 0,
        }
        plan1 = await orchestrator.think(
            "create a new Python module in project‑one",
            ctx1,
        )
        tool_call1 = code1.act(plan1, ctx1)

        # Simulate tool result for project‑one.
        result1 = ToolResult(
            success=True,
            content="created src/main.py",
            metadata={"project_id": "project-one"},
        )
        final_ctx1 = await code1.observe(result1, ctx1)
        assert final_ctx1.get("status") == "completed"
        assert final_ctx1.get("project_id") == "project-one"

        # Task 2: project‑two
        ctx2 = {
            "task_id": "p2.cross-task-1",
            "project_id": "project-two",
            "iteration": 0,
        }
        plan2 = await orchestrator.think(
            "refactor the main module in project‑two",
            ctx2,
        )
        tool_call2 = code2.act(plan2, ctx2)

        # Simulate tool result for project‑two.
        result2 = ToolResult(
            success=True,
            content="refactored src/main.js",
            metadata={"project_id": "project-two"},
        )
        final_ctx2 = await code2.observe(result2, ctx2)
        assert final_ctx2.get("status") == "completed"
        assert final_ctx2.get("project_id") == "project‑two"

        # Assert no cross‑project leakage.
        for key in ("last_result", "status"):
            val1 = final_ctx1.get(key)
            val2 = final_ctx2.get(key)
            assert val1 is not None
            assert val2 is not None
            assert val1 != val2
