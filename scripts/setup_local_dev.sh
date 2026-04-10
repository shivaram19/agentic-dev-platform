#!/usr/bin/env bash
# Agentic Development Platform - Local dev environment setup script
#
# This script:
#   - creates the default projects directory,
#   - sets up a SQLite dev database,
#   - runs Alembic migrations,
#   - creates a sample project,
#   - and prints basic usage hints.
#
# Intended to be idempotent so it can be re‑run safely.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "Setting up local development environment in $PROJECT_ROOT"

# Create default project root
DEFAULT_PROJECT_ROOT="${PROJECT_ROOT}/projects"
if [[ ! -d "$DEFAULT_PROJECT_ROOT" ]]; then
    echo "Creating projects directory: $DEFAULT_PROJECT_ROOT"
    mkdir -p "$DEFAULT_PROJECT_ROOT"
else
    echo "Using existing projects directory: $DEFAULT_PROJECT_ROOT"
fi

# Create SQLite dev.db if not present
DEV_DB="$PROJECT_ROOT/dev.sqlite3"
if [[ ! -f "$DEV_DB" ]]; then
    echo "Creating SQLite dev database: $DEV_DB"
    sqlite3 "$DEV_DB" "VACUUM;"
    echo "Database initialized at $DEV_DB"
else
    echo "Using existing database: $DEV_DB"
fi

# Run Alembic migrations
ALEMBIC_INI="$PROJECT_ROOT/alembic.ini"
if [[ ! -f "$ALEMBIC_INI" ]]; then
    echo "Error: $ALEMBIC_INI not found; run from project root or adjust path."
    exit 1
fi

echo "Running Alembic migrations"
PYTHONPATH="$PROJECT_ROOT" alembic upgrade head

# Create sample project directory
SAMPLE_PROJECT="$DEFAULT_PROJECT_ROOT/sample-app"
if [[ ! -d "$SAMPLE_PROJECT" ]]; then
    echo "Creating sample project directory: $SAMPLE_PROJECT"
    mkdir -p "$SAMPLE_PROJECT"
    cat > "$SAMPLE_PROJECT/README.md" << 'EOF'
# Sample Application

This is a sample project created by `scripts/setup_local_dev.sh`.

To let the agentic platform work on it, run:

    python main.py sample-app --task "Create a simple Python module that does X"
EOF
else
    echo "Sample project already exists: $SAMPLE_PROJECT"
fi

# Create a minimal Python module for the sample app
MODULE_FILE="$SAMPLE_PROJECT/main.py"
if [[ ! -f "$MODULE_FILE" ]]; then
    echo "Creating initial module: $MODULE_FILE"
    cat > "$MODULE_FILE" << 'EOF'
"""Sample application module created by the agentic dev platform."""

def main() -> None:
    print("Hello, Agentic World!")

if __name__ == "__main__":
    main()
EOF
fi

# Print next steps
echo "✔ Local dev environment setup complete."
echo
echo "Next steps:"
echo "  1. (Optional) install Python dependencies:"
echo "       pip install -e ."  # assume a `setup.py` or `pyproject.toml` exists
echo "  2. Run the agentic platform:"
echo "       python main.py sample-app --task \"Add a Fibonacci function to main.py\""
echo "  3. (Optional) enable voice mode if voice components are wired:"
echo "       python main.py sample-app --task \"Refactor main.py\" --voice"
echo
echo "For advanced configuration, edit config/system_config.yaml and config/agent_prompts.yaml."
