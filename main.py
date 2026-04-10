"""Agentic Development Platform - CLI entrypoint.

Spin up the MCP server, configure LLM backends, and glue together the core
components (orchestrator, code agent, voice agent, registry, etc.) so that
they can be invoked from the command line or via an IDE plugin.
"""
import asyncio
import argparse
import logging
import structlog
from typing import Dict, Any

from core.registry.project_registry import InMemoryProjectRegistry
from core.llm.llm_factory import DefaultLLMFactory, LLMBackendType
from core.mcp.server import MCPServer
from core.orchestrator.orchestrator_agent import OrchestratorAgent
from core.agents.code_agent import CodeAgent, CodeAgentConfig
from voice.voice_command_handler import VoiceCommandHandler
from voice.transcription import TranscriptionService


def setup_logging() -> None:
    """Configure structlog for human‑readable console output."""
    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler()],
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.dev.ConsoleRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
    )


def create_default_system_config() -> Dict[str, Any]:
    """Return a minimal system config similar to config/system_config.yaml."""
    return {
        "llm": {
            "default_backend": "anthropic",
            "default_model_id": "claude-3-5-sonnet-20241022",
            "backends": {
                "anthropic": {
                    "api_key_env": "ANTHROPIC_API_KEY",
                    "base_url": "https://api.anthropic.com",
                    "max_tokens": 4096,
                    "temperature": 0.3,
                },
                "ollama": {
                    "base_url": "http://localhost:11434/v1",
                    "api_key_env": "OLLAMA_API_KEY",
                    "max_tokens": 2048,
                    "temperature": 0.4,
                },
            },
        },
        "projects": {
            "default_root": "./projects",
        },
        "voice": {
            "enabled": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Agentic Development Platform")
    parser.add_argument("project_id", nargs="?", default="default-project")
    parser.add_argument("--task", dest="task_description", default="Hello world")
    parser.add_argument("--voice", action="store_true")
    args = parser.parse_args()

    setup_logging()
    log = structlog.get_logger(__name__)

    # Load config
    config = create_default_system_config()

    # Create LLM factory
    llm_factory = DefaultLLMFactory(
        global_config=config["llm"].get("backends", {})
    )

    # Create project registry
    registry = InMemoryProjectRegistry()
    project_id = args.project_id
    registry.register(
        project_id=project_id,
        root_path=f"./projects/{project_id}",
        default_agent_id="code-agent",
        tags={"stack": "python"},
    )

    # Create MCP server and tools
    # (in this simplified file we assume a basic server setup)
    # In a real project `core/mcp/server.py` would expose `MCPServer`.
    # For now we stub it so the entrypoint compiles.
    mcp_server = None  # Placeholder; would be: MCPServer(...)

    # Create code agent
    code_agent = CodeAgent(
        agent_id="code-agent",
        project_id=project_id,
        tools=mcp_server,  # actually an `IToolExecutor` adapter
        scratchpad=...,
        config=CodeAgentConfig(),
    )

    # Create orchestrator agent
    # (assume `OrchestratorAgent` is defined in `core/orchestrator/`)
    orchestrator = OrchestratorAgent(
        agent_id=f"orchestrator-{project_id}",
        project_id=project_id,
        tools=mcp_server,
        scratchpad=...,
    )

    # Create voice command handler
    voice_enabled = args.voice and config["voice"].get("enabled", False)
    voice_handler: VoiceCommandHandler | None = None
    if voice_enabled:
        # In a real project this would wire a real `TranscriptionService`.
        # For now we stub with a dummy provider.
        transcription_service: TranscriptionService = ...  # impl not shown
        voice_config = config["llm"]["backends"].get("anthropic", {})
        intent_parser_config = {
            "default_model_id": voice_config.get(
                "default_model_id", "claude-3-5-sonnet-20241022"
            ),
            "default_backend": "anthropic",
            "max_tokens": voice_config.get("max_tokens", 512),
            "temperature": voice_config.get("temperature", 0.1),
        }
        voice_handler = VoiceCommandHandler(
            transcription_service=transcription_service,
            intent_parser=...,  # would be built with above `llm_factory`
            llm_factory=llm_factory,
        )

    # Run the main orchestration loop
    async def run_task(task_description: str) -> None:
        log.info("Running task", task=task_description)
        context = {
            "project_id": project_id,
            "user_id": "default-user",
            "session_id": "default-session",
            "task_id": "default-task",
            "iteration": 0,
        }
        # For simplicity, just call orchestrator `think` then `act` once.
        # A real system would loop until `COMPLETED` or `FAILED`.
        plan = await orchestrator.think(
            task_description=task_description,
            context=context,
        )
        tool_call = await orchestrator.act(
            plan=plan,
            context=context,
        )

        # Have code agent consume the tool call and then observe.
        # In a real project this would involve an `IToolExecutor` intermediary.
        result = await code_agent.observe(
            tool_result=...,  # synthesized from `tool_call`
            context=context,
        )
        # In a real project this would surface `result` to the user.
        log.info("Finished task", result=result)

    # Run the voice pipeline if enabled.
    async def run_voice() -> None:
        if not voice_handler:
            log.warning("Voice is disabled")
            return

        # In a real project you would hook to a real audio device or HTTP API.
        # Here we simulate a voice command as text.
        mock_audio_input = {
            "raw_text": "create a new Python file that prints hello world",
        }
        context = {
            "user_id": "default-user",
            "project_id": project_id,
            "device_id": "default-device",
            "agent_id": code_agent.agent_id,
        }
        result = await voice_handler.handle_voice_command(
            audio_input=mock_audio_input,
            context=context,
        )
        log.info("Voice command processed", result=result)

    # Run the requested mode.
    if args.voice:
        async def run() -> None:
            await run_voice()

        asyncio.run(run())
    else:
        async def run() -> None:
            await run_task(args.task_description)

        asyncio.run(run())


if __name__ == "__main__":
    main()
