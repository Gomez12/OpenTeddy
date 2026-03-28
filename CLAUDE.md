# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenTeddy is a Python-based agentic AI project built on the `deepagents` framework (LangChain/LangGraph). It specialises in ETIM product classification using semantic search over a LanceDB vector database, with code execution in an isolated Docker sandbox.

## Development Setup

- Python 3.11, managed via `uv`
- Install dependencies: `uv sync`
- Environment variables loaded from `.env` via `python-dotenv`

## Commands

```bash
# Run the agent (interactive default query)
uv run agentic/agent.py

# Run the agent with a custom query (text-only output)
uv run agentic/agent.py "classify a LED lamp"

# Start all services (OpenSandbox + Embedding server)
./startserver.sh

# Build the custom Docker sandbox image
./createdockerimage.sh

# Rebuild ETIM LanceDB from upstream XML
uv run python build_etim_lancedb.py

# Search/install skills from skills.sh
uv run skills_manager.py search "python testing"
uv run skills_manager.py install owner/repo -g -s skill-name
```

## Architecture

### Agent (`agentic/agent.py`)

Central orchestrator using `deepagents.create_deep_agent()`. Loads tools via `importlib` (because skill directories use hyphens, not valid Python package names). Configures a `CompositeBackend` for virtual filesystem routing and connects to an LLM via `OPENAI_API_BASE`.

The agent has 8 tools registered: `search_etim_groups`, `search_etim_classes`, `run_code`, `run_shell`, `write_sandbox_file`, `read_sandbox_file`, `export_from_sandbox`, `import_to_sandbox`.

When invoked with CLI arguments, only the final text response is printed (reasoning blocks filtered out). Without arguments, the full result object is printed.

### CompositeBackend file routing

The agent uses `CompositeBackend` to map virtual paths to physical directories:

| Virtual path | Physical path | Access |
|---|---|---|
| `/files/in/` | `agentic/general/files/in/` | Read-only (`ReadOnlyBackend` wrapper) |
| `/files/out/` | `agentic/general/files/out/` | Read-write |
| `/files/tmp/` | `agentic/general/files/tmp/` | Read-write |
| `/skills/` | `agentic/general/skills/` | Read-write (skill loading) |

The `skills=["/skills/"]` parameter uses this virtual path so the `SkillsMiddleware` can discover SKILL.md files via the backend.

### Skills (`agentic/general/skills/`)

Each skill is a subdirectory with a `SKILL.md` (YAML frontmatter required: `name`, `description`). The agent loads skill metadata on first invocation and injects it into the system prompt. Skills follow progressive disclosure: the agent reads the full SKILL.md only when a task matches.

Key skill: `etim-lookup` — instructs the agent to perform at least 5 semantically different searches with `top_k=50`, work top-down (groups then classes), and return JSON output with group, class, features, and confidence.

### Sandbox tools (`agentic/general/tools/sandbox.py`)

Connects to an OpenSandbox server (Docker-based). A persistent sandbox instance is reused across calls. Binary file workflow: generate files in the sandbox with `run_code`, then use `export_from_sandbox` to copy them to the local `/files/out/` directory. The built-in `write_file` tool only handles text, so `export_from_sandbox` is the only way to produce binary outputs (xlsx, pdf, images).

### Embedding search (`agentic/general/skills/etim-lookup/etim_search.py`)

Performs vector similarity search over LanceDB (`agentic/general/lancedbs/etimdynamic/`). Prefers the embedding API server (`EMBED_API_BASE`) when available, falls back to loading the sentence-transformers model locally. The LanceDB contains 171 ETIM groups and 5720 ETIM classes with multilingual-e5-base embeddings.

### Servers

- **OpenSandbox** (port 8080) — Docker-based code execution. Config in `.sandbox.toml`.
- **Embedding server** (port 8100) — FastAPI with OpenAI-compatible `/v1/embeddings` endpoint. Serves `multilingual-e5-base` model. Source: `agentic/servers/embedding_server.py`.

Both started together via `startserver.sh`, which monitors processes and shuts down cleanly on Ctrl-C.

### Logger (`agentic/logger.py`)

`LLMLogger` callback handler that writes all LLM communication to timestamped JSONL files in `agentic/logs/`. Logs chat_model_start, llm_end, tool_start/end, and chain events with run_id correlation. Note: `serialized` can be `None` in chain events — handled with `(serialized or {}).get(...)`.

### Docker image (`docker/dockerfile`)

Custom image `openteddy/sandbox` based on `opensandbox/code-interpreter:v1.0.2`. Pre-installs Python packages (openpyxl, pandas, matplotlib, requests, etc.), system tools (ffmpeg, imagemagick, graphviz), and Chromium + agent-browser for browser automation. Built with `./createdockerimage.sh`. The Python in the base image is at `/opt/python/versions/cpython-3.14.2-linux-aarch64-gnu/bin/` and needs `--break-system-packages` for pip.

### Skills Manager (`skills_manager.py`)

CLI tool with three commands: `search` (queries skills.sh API), `info` (clones repo, lists skills), `install` (copies skill directories). Supports `-g` for general install and `-u <user>` for user-specific install.

## Key Environment Variables (.env)

| Variable | Purpose |
|---|---|
| `OPENAI_API_BASE` | LLM API endpoint |
| `OPENAI_MODEL` | Model name for the agent |
| `EMBED_API_BASE` | Embedding server URL (http://localhost:8100) |
| `EMBED_MODEL` | Local model path for fallback |
| `SANDBOX_IMAGE` | Docker image for sandbox (openteddy/sandbox:latest) |
| `DOCKER_HOST` | Docker socket path |
