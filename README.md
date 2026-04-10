# Agentic Development Platform

An AI-driven, multi-agent system that automates software development workflows by combining LLM-based agents with secure tool execution and persistent project management.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

## 🎯 Overview

The Agentic Development Platform empowers developers to express high-level requirements and let AI agents handle the implementation details. Whether it's code generation, testing, documentation, or refactoring, the platform orchestrates specialized agents to work together in a coordinated, auditable manner.

**Key Capabilities:**
- 🤖 **Multi-Agent Orchestration**: Coordinate specialized agents (Code, Database, API, Test, Security, Orchestrator)
- 🔌 **Model Context Protocol (MCP)**: Secure, sandboxed tool execution for file operations, shell commands, and git
- 🗣️ **Voice Control**: Hands-free task initiation via voice commands with NLU intent parsing
- 🧠 **Persistent Memory**: Scratchpad system for task context and audit trails
- 🔄 **Multi-Project Support**: Registry-based project isolation and cross-project coordination
- 🔌 **Pluggable LLMs**: Support for Anthropic Claude, Ollama, and custom providers
- 📊 **Observable**: Built-in monitoring with Prometheus/Grafana dashboards

---

## 🏗️ Architecture

### Core Components

```
┌─────────────────────────────────────────────────────┐
│          CLI / IDE Plugin / Voice Input              │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│         Orchestrator Agent                           │
│    (Task decomposition & routing)                    │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│    Specialized Agents (Think-Act-Observe)            │
│  ┌──────────────┬──────────────┬──────────────┐    │
│  │ Code Agent   │ Test Agent   │ DB Agent     │    │
│  │ API Agent    │ Security Agnt│ ...          │    │
│  └──────────────┴──────────────┴──────────────┘    │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│   Model Context Protocol (MCP) Server               │
│  ┌──────────────┬──────────────┬──────────────┐    │
│  │ Filesystem   │ Shell        │ Git          │    │
│  │ Server       │ Server       │ Server       │    │
│  └──────────────┴──────────────┴──────────────┘    │
└────────────────────┬────────────────────────────────┘
                     │
         ┌───────────┴──────────────┐
         │                          │
    ┌────▼────┐          ┌─────────▼────┐
    │ File    │          │ Shell Cmds   │
    │ System  │          │ Git Ops      │
    └─────────┘          └──────────────┘
```

### Think-Act-Observe Pattern

All agents implement the T-A-O lifecycle:
1. **Think**: Analyze task, create plan
2. **Act**: Select and invoke MCP tools
3. **Observe**: Process results, update context

### Communication & State

- **Message Bus**: Kafka-based async communication for distributed deployments
- **State Management**: Redis for shared agent context
- **Persistence**: SQLAlchemy + Alembic for database schema versioning

---

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- Docker & Docker Compose (optional, for containerized setup)
- API keys for Claude (ANTHROPIC_API_KEY) or Ollama installation

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/shivaram19/agentic-dev-platform.git
   cd agentic-dev-platform
   ```

2. **Set up environment**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and configuration
   ```

3. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **Initialize database**
   ```bash
   alembic upgrade head
   ```

### Docker Setup (Optional)

```bash
docker-compose up -d
```

This starts the application with Redis, Kafka, and PostgreSQL in containers.

---

## 💡 Usage Examples

### CLI Mode

Execute a task with the orchestrator:
```bash
python main.py my-project --task "Create a Python function that validates email addresses and add tests"
```

### Voice Mode

Start the voice pipeline:
```bash
python main.py my-project --voice
```

Then speak your requirements naturally. The system will transcribe, parse intent, and execute.

### Create a New Project

```bash
python scripts/create_project.py --name "my-new-project" --stack "python"
```

---

## 📁 Project Structure

```
agentic-dev-platform/
├── README.md                          # This file
├── main.py                            # CLI entrypoint
├── pyproject.toml                     # Project metadata
├── requirements.txt                   # Python dependencies
├── .env.example                       # Environment template
├── Dockerfile                         # Container image
├── docker-compose.yml                 # Service orchestration
│
├── config/                            # Configuration files
│   ├── system_config.yaml             # LLM backends, logging
│   └── agent_prompts.yaml             # Agent system prompts
│
├── core/                              # Core platform code
│   ├── agents/                        # Specialized agent implementations
│   │   ├── base.py                    # BaseAgent (T-A-O pattern)
│   │   ├── code_agent.py              # Code generation & modification
│   │   ├── db_agent.py                # Database design & optimization
│   │   ├── api_agent.py               # REST/GraphQL integration
│   │   ├── test_agent.py              # Test automation
│   │   ├── security_agent.py          # Security & threat modeling
│   │   └── agent_pool.py              # Concurrent execution
│   │
│   ├── orchestrators/                 # Task orchestration
│   │   ├── base.py                    # BaseOrchestrator
│   │   ├── project_orchestrator.py    # Single-project task routing
│   │   └── master_orchestrator.py     # Multi-project coordination
│   │
│   ├── mcp/                           # Model Context Protocol
│   │   ├── mcp_client.py              # MCP client
│   │   ├── protocol.py                # Message definitions
│   │   └── servers/                   # MCP server implementations
│   │       ├── filesystem_server.py   # File operations
│   │       ├── shell_server.py        # Command execution
│   │       └── git_server.py          # Git operations
│   │
│   ├── llm/                           # LLM provider abstractions
│   │   ├── llm_provider.py            # Abstract LLM interface
│   │   ├── claude_provider.py         # Anthropic Claude
│   │   ├── ollama_provider.py         # Ollama integration
│   │   └── llm_factory.py             # Provider factory
│   │
│   ├── communication/                 # Async communication
│   │   ├── message_bus.py             # Abstract message bus
│   │   ├── kafka_bus.py               # Kafka implementation
│   │   └── redis_state.py             # Redis state management
│   │
│   ├── models/                        # SQLAlchemy data models
│   │   ├── task_model.py              # Task lifecycle tracking
│   │   └── session_model.py           # Session management
│   │
│   ├── registry/                      # Project registry
│   │   └── project_registry.py        # Project discovery & management
│   │
│   ├── scratchpad/                    # Persistent working memory
│   │   ├── scratchpad_manager.py      # Context & audit logs
│   │   └── templates/                 # Task templates
│   │
│   └── langgraph/                     # Workflow graph
│       └── agent_graph.py             # State machine execution
│
├── voice/                             # Voice command support
│   ├── transcription.py               # Audio-to-text (Whisper API)
│   ├── intent_parser.py               # Command intent extraction
│   └── voice_command_handler.py       # Pipeline orchestration
│
├── tests/                             # Test suite
│   ├── unit/                          # Unit tests
│   │   ├── test_base_agent.py
│   │   ├── test_mcp_client.py
│   │   └── test_orchestrators.py
│   ├── integration/                   # Integration tests
│   │   └── test_cross_project.py
│   └── fixtures/                      # Test fixtures
│       └── sample_tasks.py
│
├── scripts/                           # Utility scripts
│   ├── create_project.py              # New project scaffolding
│   └── setup_local_dev.sh             # Development environment setup
│
├── docs/                              # Documentation
│   ├── architecture.md                # System design & components
│   ├── agent_development_guide.md     # Guide for building agents
│   └── mcp_server_development.md      # MCP server implementation
│
├── monitoring/                        # Observability
│   ├── prometheus.yml                 # Metrics configuration
│   └── grafana_dashboards/            # Pre-built dashboards
│
├── alembic/                           # Database migrations
│   ├── env.py
│   ├── alembic.ini
│   └── versions/
│
├── projects/                          # User projects (isolated)
└── registry/                          # Agent registry
```

---

## 🔧 Core Concepts

### Agents

Each agent specializes in a domain:

| Agent | Purpose |
|-------|---------|
| **CodeAgent** | Code generation, modification, refactoring |
| **TestAgent** | Test case generation, coverage analysis |
| **DatabaseAgent** | Schema design, query optimization |
| **APIAgent** | REST/GraphQL endpoint design |
| **SecurityAgent** | Vulnerability detection, threat modeling |
| **OrchestratorAgent** | Task decomposition, routing, coordination |

### LLM Backends

Configure your preferred LLM provider in `config/system_config.yaml`:

```yaml
llm:
  default_backend: "anthropic"  # or "ollama"
  backends:
    anthropic:
      api_key_env: "ANTHROPIC_API_KEY"
      model_id: "claude-3-5-sonnet-20241022"
      temperature: 0.3
    ollama:
      base_url: "http://localhost:11434/v1"
      model_id: "mistral"
```

### Tool Execution (MCP)

Tools are invoked securely through the MCP protocol:

```python
# Tool invocation in an agent
tool_call = {
    "tool": "filesystem.write_file",
    "args": {
        "path": "app.py",
        "content": "print('Hello')"
    }
}
result = await mcp_client.invoke(tool_call, project_id)
```

### Scratchpad & Audit Trail

Every task creates an audit trail in the scratchpad:

```
Task scratchpad

Project ID: my-project
Agent ID: code-agent
Task ID: task-123
Started: 2024-04-10T14:30:00Z

## Task description
Create a Python function for email validation

## Plan
1. Write email regex pattern
2. Create validate_email function
3. Add docstring and type hints

## Observations
- Step 1 complete: regex pattern validated
- Step 2 complete: function created
- Tests passing: 5/5

## Result
Function created at src/validators/email.py
```

---

## 🧪 Testing

Run the test suite:

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/

# Integration tests
pytest tests/integration/

# With coverage
pytest --cov=core tests/
```

---

## 📊 Monitoring

### Local Development

Access Grafana dashboards at `http://localhost:3000` (when using Docker Compose).

### Key Metrics

- Agent latency per task
- Tool execution success rates
- Token usage by LLM backend
- Error rates by component

Configure additional metrics in `monitoring/prometheus.yml`.

---

## 🔐 Security

### Sandboxed Tool Execution

- **Filesystem**: Operations scoped to project directory
- **Shell**: Command whitelist and resource limits
- **Git**: Branch protection and commit validation

### Secrets Management

Store sensitive data in `.env`:
```bash
ANTHROPIC_API_KEY=sk-...
OLLAMA_API_KEY=...
DATABASE_URL=postgresql://...
```

Never commit `.env` or credentials files (see `.gitignore`).

---

## 📖 Documentation

- **[Architecture Guide](./docs/architecture.md)** – System design, components, workflows
- **[Agent Development](./docs/agent_development_guide.md)** – Build custom agents
- **[MCP Servers](./docs/mcp_server_development.md)** – Implement new tools

---

## 🤝 Contributing

1. **Fork** the repository
2. **Create a feature branch**: `git checkout -b feat/my-feature`
3. **Make changes** and add tests
4. **Run test suite**: `pytest`
5. **Commit** with clear messages following conventional commits
6. **Push** and open a Pull Request

### Code Style

- Python: PEP 8 via `black` and `flake8`
- Type hints required for public functions
- Docstrings for all modules and classes

---

## 🚢 Deployment

### Local Development
```bash
python main.py my-project --task "Your task here"
```

### Docker
```bash
docker-compose up
python main.py my-project --task "Your task here"
```

### Production

1. Configure environment variables
2. Set up PostgreSQL database
3. Run migrations: `alembic upgrade head`
4. Deploy using Docker or Kubernetes
5. Monitor with Grafana dashboards

---

## 📝 License

This project is licensed under the MIT License – see [LICENSE](./LICENSE) file for details.

---

## 🆘 Support

- 📚 Read the [documentation](./docs/)
- 🐛 Report issues on [GitHub Issues](https://github.com/shivaram19/agentic-dev-platform/issues)
- 💬 Discuss ideas in [GitHub Discussions](https://github.com/shivaram19/agentic-dev-platform/discussions)

---

## 🎓 Learn More

- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) – Tool abstraction standard
- [LangGraph](https://langchain-ai.github.io/langgraph/) – Workflow orchestration
- [Anthropic Claude](https://docs.anthropic.com/) – LLM documentation
- [Alembic](https://alembic.sqlalchemy.org/) – Database migrations

---

**Built with** 🤖 + 🧠 + ❤️
