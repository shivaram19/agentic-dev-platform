# Agentic Development Platform – Architecture Overview

The Agentic Development Platform is an AI‑driven, multi‑agent system that automates software development workflows by combining LLM‑based agents with a secure middleware layer (MCP) and a persistent project registry.

## Core Components

### 1. Multi‑Agent Coordination Protocol (MCP) Server
The MCP server exposes a set of tools (e.g., `filesystem.read_file`, `filesystem.write_file`, `test_runner.run`) as a uniform API that agents can invoke. This protocol decouples agent logic from the underlying implementation and allows tool reuse across different agents and orchestrators.

- **Tool Abstraction**: Each tool is defined by a contract (`ToolCall` / `ToolResult`) and metadata.
- **Transport Agnostic**: The MCP can be exposed over HTTP, WebSocket, or in‑process, enabling both local and remote deployments.
- **Security Boundaries**: File‑system and execution operations are sandboxed and permission‑scoped per project.

### 2. Agents and the T‑A‑O Pattern
All agents implement the *Think–Act–Observe* (T‑A‑O) pattern inherited from the base `BaseAgent`:

- **`think`**: analyzes a task description and context, producing a plan dictionary suitable for `act`.
- **`act`**: decides which MCP tool to call and with which arguments.
- **`observe`**: consumes the `ToolResult` to update the internal state and context.

Specialized agents build on this pattern:

- **`CodeAgent`**: focuses on code generation, modification, and light‑weight refactoring.
- **`OrchestratorAgent`**: decomposes complex tasks into sub‑tasks and routes them to domain‑specific agents (e.g., code, test, refactoring, documentation).
- **`VoiceCommandHandler`**: translates spoken instructions into structured tasks for the orchestrator using an LLM‑based intent parser.

### 3. Project Registry and Metadata
The project registry (`core/registry/project_registry.py`) tracks:

- Registered project IDs and their root directories.
- Default agents and tags (e.g., `{"stack": "python", "owner": "team‑a"}`).
- Dependencies and cross‑project references.

The registry is implemented as both an in‑memory store for development and a DB‑backed store for production.

### 4. Scratchpad and Context Persistence
The scratchpad (`core/scratchpad/scratchpad_manager.py`) provides a time‑based, append‑only log of:

- Task plans created by `think`.
- Tool results and agent observations.
- Errors and intermediate decisions.

Entries are partitioned by:

- `project_id`
- `agent_id`
- `task_id`
- `section` (e.g., `"Plan"`, `"Observations"`)

This enables auditing, replay, and debugging without coupling to the agent implementation.

### 5. LLM Integration and Prompts
LLM interactions are routed through:

- `LLMClient` abstractions that encapsulate model‑specific APIs.
- Prompt templates defined in `config/agent_prompts.yaml` (e.g., task‑decomposition prompts for the orchestrator, code‑generation prompts for `CodeAgent`).

Clients are configured via `config/system_config.yaml` with:

- Default LLM backend (e.g., `anthropic` or `ollama`).
- Per‑backend options like `max_tokens` and `temperature`.
- Secret‑key environment variables.

### 6. Testing and Validation Architecture

Integration tests verify:

- Cross‑project isolation via multiple `InMemoryProjectRegistry` instances.
- MCP‑tool round‑trips using stub executors.
- Scratchpad partitioning and log‑replay.

Fixtures in `tests/fixtures/sample_tasks.py` define reusable task shapes that are shared across unit and integration tests.

## Deployment and Workflows

- **CLI Mode**: `python main.py <project_id> --task "..."` starts the MCP server, loads the registry, and runs a single agent loop.
- **IDE Plugin Mode**: An IDE plugin communicates with the MCP server via HTTP and delegates code‑related tasks to agents.
- **Voice Mode**: `python main.py <project_id> --voice` activates the voice pipeline, where audio input flows through transcription and intent‑parsing before entering the orchestrator.

Together, this architecture enables a developer to express high‑level requirements (textual or spoken) and let agentic workflows handle files, tests, documentation, and refactoring while preserving project‑level isolation and auditability.
