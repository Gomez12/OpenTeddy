"""
Base agent factory with all shared infrastructure.

Provides create_agent() which sets up tools, backends, skills, and logging.
Specific agents only need to provide a system_prompt and optionally extra tools.
"""

import os
import sys
import time
import importlib.util
from pathlib import Path

from dotenv import load_dotenv
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.backends.composite import CompositeBackend
from langgraph.checkpoint.memory import MemorySaver

load_dotenv()

# --- Module loader (needed because skill dirs use hyphens) ---

def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_AGENTIC_DIR = Path(__file__).resolve().parent
_GENERAL_DIR = _AGENTIC_DIR / "general"

_etim_search = _load_module("etim_search", _GENERAL_DIR / "skills" / "etim-lookup" / "etim_search.py")
_sandbox = _load_module("sandbox", _GENERAL_DIR / "tools" / "sandbox.py")
_readonly_mod = _load_module("readonly_backend", _GENERAL_DIR / "tools" / "readonly_backend.py")

SHARED_TOOLS = [
    _etim_search.search_etim_groups,
    _etim_search.search_etim_classes,
    _etim_search.get_class_features,
    _sandbox.run_code,
    _sandbox.run_shell,
    _sandbox.write_sandbox_file,
    _sandbox.read_sandbox_file,
    _sandbox.export_from_sandbox,
    _sandbox.import_to_sandbox,
]

ReadOnlyBackend = _readonly_mod.ReadOnlyBackend

SKILLS_DIR = str(_GENERAL_DIR / "skills")
FILES_DIR = str(_GENERAL_DIR / "files")

SKILLS_PROMPT = (
    "SKILLS — IMPORTANT:\n"
    "Before performing any task, ALWAYS check if there is a matching skill available.\n"
    "If a skill exists for the task, you MUST read its SKILL.md first and follow its instructions.\n"
    "Never skip the skill — even if you think you can do it faster without it.\n"
)

FILE_HANDLING_PROMPT = (
    "FILE HANDLING — IMPORTANT:\n"
    "When you need to create output files (xlsx, pdf, csv, images, etc.):\n"
    "1. Use run_shell() to install any needed packages in the sandbox\n"
    "2. Use run_code() to generate the file inside the sandbox (write to /tmp/)\n"
    "3. Use export_from_sandbox() to copy the file to the local output directory\n"
    "This is the ONLY way to create files that the user can access.\n"
    "Do NOT use the built-in write_file tool for binary files — it only handles text.\n"
    "Do NOT write files to the virtual filesystem — use the sandbox + export workflow instead.\n\n"
    "When you need to read input files provided by the user:\n"
    "- Use import_to_sandbox() to copy them from /files/in/ into the sandbox\n\n"
    "Local filesystem directories (for reading text files only):\n"
    "- /files/in/ — read-only input files\n"
    "- /files/out/ — output directory (but use export_from_sandbox for binary files)\n"
    "- /files/tmp/ — temp directory\n"
)

BASE_PROMPT = f"{SKILLS_PROMPT}\n{FILE_HANDLING_PROMPT}"


def create_agent(system_prompt: str, extra_tools: list | None = None):
    """Create a deep agent with all shared infrastructure.

    Args:
        system_prompt: The agent-specific system prompt. The shared skills and
            file handling instructions are automatically appended.
        extra_tools: Optional list of additional tools beyond the shared set.

    Returns:
        A configured deep agent ready to invoke.
    """
    tools = SHARED_TOOLS + (extra_tools or [])
    full_prompt = f"{system_prompt}\n\n{BASE_PROMPT}"

    return create_deep_agent(
        model=f"openai:{os.environ['OPENAI_MODEL']}",
        tools=tools,
        system_prompt=full_prompt,
        backend=CompositeBackend(
            default=FilesystemBackend(root_dir=".", virtual_mode=True),
            routes={
                "/files/in/": ReadOnlyBackend(
                    FilesystemBackend(root_dir=f"{FILES_DIR}/in", virtual_mode=True)
                ),
                "/files/out/": FilesystemBackend(root_dir=f"{FILES_DIR}/out", virtual_mode=True),
                "/files/tmp/": FilesystemBackend(root_dir=f"{FILES_DIR}/tmp", virtual_mode=True),
                "/skills/": FilesystemBackend(root_dir=SKILLS_DIR, virtual_mode=True),
            },
        ),
        skills=["/skills/"],
        checkpointer=MemorySaver(),
    )


def _get_callbacks():
    """Build the list of callback handlers (JSONL logger + Langfuse if configured)."""
    from logger import LLMLogger

    callbacks = [LLMLogger()]

    if os.environ.get("LANGFUSE_HOST"):
        try:
            from langfuse.langchain import CallbackHandler as LangfuseHandler

            handler = LangfuseHandler()
            callbacks.append(handler)
        except Exception as e:
            print(f"Warning: Langfuse init failed: {e}")

    return callbacks


def _flush_callbacks(callbacks):
    """Flush any buffered callback handlers (e.g. Langfuse)."""
    for cb in callbacks:
        if hasattr(cb, "flush"):
            cb.flush()


def run_agent(agent, default_query: str = "Hallo, wat kan je voor me doen?", query: str | None = None):
    """Run an agent from the command line with logging and timing.

    Args:
        agent: The agent to invoke.
        default_query: Fallback query when no CLI args and no explicit query.
        query: Explicit query string. If provided, CLI args are ignored and
            output is text-only (same as CLI arg mode).
    """
    if query is not None:
        text_only = True
    elif len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        text_only = True
    else:
        query = default_query
        text_only = False

    callbacks = _get_callbacks()
    start = time.time()
    result = agent.invoke(
        {"messages": [{"role": "user", "content": query}]},
        config={
            "configurable": {"thread_id": "demo"},
            "callbacks": callbacks,
            "recursion_limit": 100,
        },
    )
    _flush_callbacks(callbacks)
    elapsed = time.time() - start
    if text_only:
        content = result["messages"][-1].content
        if isinstance(content, list):
            print("\n".join(block["text"] for block in content if block.get("type") == "text"))
        else:
            print(content)
    else:
        print(result)
    minutes, seconds = divmod(elapsed, 60)
    print(f"\n⏱ Runtime: {int(minutes)}m {seconds:.1f}s")
