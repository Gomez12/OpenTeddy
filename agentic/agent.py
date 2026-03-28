import os
from pathlib import Path

from dotenv import load_dotenv
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.backends.composite import CompositeBackend
from langgraph.checkpoint.memory import MemorySaver

load_dotenv()

import importlib.util

def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_tools_dir = Path(__file__).resolve().parent / "general"
_etim_search = _load_module("etim_search", _tools_dir / "skills" / "etim-lookup" / "etim_search.py")
search_etim_groups = _etim_search.search_etim_groups
search_etim_classes = _etim_search.search_etim_classes

_sandbox = _load_module("sandbox", _tools_dir / "tools" / "sandbox.py")
run_code = _sandbox.run_code
run_shell = _sandbox.run_shell
write_sandbox_file = _sandbox.write_sandbox_file
read_sandbox_file = _sandbox.read_sandbox_file
export_from_sandbox = _sandbox.export_from_sandbox
import_to_sandbox = _sandbox.import_to_sandbox

_readonly_mod = _load_module("readonly_backend", _tools_dir / "tools" / "readonly_backend.py")
ReadOnlyBackend = _readonly_mod.ReadOnlyBackend

SKILLS_DIR = str(Path(__file__).resolve().parent / "general" / "skills")
FILES_DIR = str(Path(__file__).resolve().parent / "general" / "files")

agent = create_deep_agent(
    model=f"openai:{os.environ['OPENAI_MODEL']}",
    tools=[search_etim_groups, search_etim_classes, run_code, run_shell, write_sandbox_file, read_sandbox_file, export_from_sandbox, import_to_sandbox],
    system_prompt=(
        "You are a helpful assistant that specialises in ETIM product classification.\n\n"
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
    ),
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

if __name__ == "__main__":
    import sys
    from logger import LLMLogger

    has_arg = len(sys.argv) > 1
    query = " ".join(sys.argv[1:]) if has_arg else "Classificeer een stopcontact met randaarde"
    logger = LLMLogger()
    result = agent.invoke(
        {"messages": [{"role": "user", "content": query}]},
        config={"configurable": {"thread_id": "demo"}, "callbacks": [logger]},
    )
    if has_arg:
        content = result["messages"][-1].content
        if isinstance(content, list):
            print("\n".join(block["text"] for block in content if block.get("type") == "text"))
        else:
            print(content)
    else:
        print(result)
