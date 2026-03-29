"""
OpenSandbox tools for executing code in an isolated sandbox environment.

Connects to a local OpenSandbox server (configured via .sandbox.toml)
and provides tools for running code, shell commands, and file operations.
"""

import os
from datetime import timedelta
from pathlib import Path

from opensandbox.sync import SandboxSync
from opensandbox.config.connection_sync import ConnectionConfigSync
from opensandbox.models.execd import RunCommandOpts

_sandbox: SandboxSync | None = None

SANDBOX_IMAGE = os.environ.get("SANDBOX_IMAGE", "opensandbox/code-interpreter:v1.0.2")
SANDBOX_HOST = os.environ.get("SANDBOX_HOST", "localhost")
SANDBOX_PORT = os.environ.get("SANDBOX_PORT", "8080")
FILES_OUT_DIR = Path(__file__).resolve().parent.parent / "files" / "out"
FILES_IN_DIR = Path(__file__).resolve().parent.parent / "files" / "in"
DEFAULT_TIMEOUT = timedelta(seconds=int(os.environ.get("SANDBOX_TIMEOUT", "120")))


def _get_sandbox() -> SandboxSync:
    """Get or create a persistent sandbox instance."""
    global _sandbox
    if _sandbox is None:
        config = ConnectionConfigSync(
            domain=f"{SANDBOX_HOST}:{SANDBOX_PORT}",
            protocol="http",
        )
        _sandbox = SandboxSync.create(
            SANDBOX_IMAGE,
            timeout=timedelta(minutes=30),
            connection_config=config,
        )
    return _sandbox


def run_code(code: str, language: str = "python") -> str:
    """Execute code in an isolated sandbox and return the output.

    Use this tool to run code safely in a sandboxed environment.
    The sandbox persists across calls so variables and files are retained.

    IMPORTANT: You have full control over the sandbox. If a package is missing,
    install it first using run_shell (e.g. run_shell("pip install openpyxl")).
    Always install required packages before running code that depends on them.

    IMPORTANT: The sandbox filesystem is isolated from the local filesystem.
    If your code creates output files (xlsx, pdf, csv, images, etc.) you MUST
    use export_from_sandbox() afterwards to copy them to the local output directory.
    Files left in the sandbox are NOT accessible to the user.
    Typical workflow:
    1. run_shell("pip install openpyxl") — install packages
    2. run_code("...code that creates /tmp/output.xlsx...") — generate the file in /tmp/
    3. export_from_sandbox("/tmp/output.xlsx", "output.xlsx") — export to local /files/out/

    Supported languages: python, javascript, typescript, bash, java, go.

    Args:
        code: The source code to execute.
        language: Programming language (default: python).

    Returns:
        The stdout output, execution results, and any errors.
    """
    sandbox = _get_sandbox()
    result = sandbox.commands.run(
        f"cat <<'CODEEOF' > /tmp/run_code.{'py' if language == 'python' else language}\n{code}\nCODEEOF"
    )

    lang_cmds = {
        "python": "python3 /tmp/run_code.py",
        "javascript": "node /tmp/run_code.javascript",
        "typescript": "npx tsx /tmp/run_code.typescript",
        "bash": "bash /tmp/run_code.bash",
        "java": "java /tmp/run_code.java",
        "go": "go run /tmp/run_code.go",
    }
    cmd = lang_cmds.get(language, f"python3 /tmp/run_code.py")
    result = sandbox.commands.run(cmd, opts=RunCommandOpts(timeout=DEFAULT_TIMEOUT))

    output_parts = []
    if result.logs.stdout:
        output_parts.append("".join(m.text for m in result.logs.stdout))
    if result.logs.stderr:
        output_parts.append("STDERR:\n" + "".join(m.text for m in result.logs.stderr))
    if result.error:
        output_parts.append(f"ERROR: {result.error.name}: {result.error.value}")
    if result.exit_code and result.exit_code != 0:
        output_parts.append(f"Exit code: {result.exit_code}")

    return "\n".join(output_parts) if output_parts else "(no output)"


def run_shell(command: str) -> str:
    """Execute a shell command in the sandbox and return the output.

    Use this for installing packages, file manipulation, or any shell operation.
    The sandbox is fully isolated — you can install anything you need with
    pip install, apt-get install, npm install, etc.

    Always install required packages before running code that depends on them.
    For example: run_shell("pip install openpyxl pandas") before generating Excel files.

    IMPORTANT: The sandbox filesystem is isolated from the local filesystem.
    If your command creates output files, use export_from_sandbox() afterwards
    to copy them to the local output directory. Files left in the sandbox are
    NOT accessible to the user.

    Args:
        command: The shell command to execute.

    Returns:
        The combined stdout/stderr output and exit code.
    """
    sandbox = _get_sandbox()
    result = sandbox.commands.run(command, opts=RunCommandOpts(timeout=DEFAULT_TIMEOUT))

    output_parts = []
    if result.logs.stdout:
        output_parts.append("".join(m.text for m in result.logs.stdout))
    if result.logs.stderr:
        output_parts.append("STDERR:\n" + "".join(m.text for m in result.logs.stderr))
    if result.exit_code and result.exit_code != 0:
        output_parts.append(f"Exit code: {result.exit_code}")

    return "\n".join(output_parts) if output_parts else "(no output)"


def write_sandbox_file(path: str, content: str) -> str:
    """Write a file to the sandbox filesystem.

    Args:
        path: Absolute path in the sandbox where the file should be written.
        content: The file content to write.

    Returns:
        Confirmation message.
    """
    sandbox = _get_sandbox()
    sandbox.files.write_file(path, content)
    return f"File written to {path}"


def read_sandbox_file(path: str) -> str:
    """Read a file from the sandbox filesystem.

    Args:
        path: Absolute path in the sandbox to read.

    Returns:
        The file content as a string.
    """
    sandbox = _get_sandbox()
    return sandbox.files.read_file(path)


def export_from_sandbox(sandbox_path: str, filename: str) -> str:
    """Copy a file from the sandbox to the local /files/out/ directory.

    Use this to export any file (including binary files like .xlsx, .pdf, .png)
    from the sandbox to the local output directory where the user can access it.

    IMPORTANT: For binary files (xlsx, pdf, images, etc.) this is the ONLY way
    to get them out of the sandbox. The regular write_file tool only handles text.

    Typical workflow:
    1. run_shell("pip install openpyxl") — install packages
    2. run_code("...code that creates /tmp/output.xlsx...") — generate the file
    3. export_from_sandbox("/tmp/output.xlsx", "output.xlsx") — export to local

    Args:
        sandbox_path: Absolute path of the file inside the sandbox.
        filename: Name for the file in the local output directory (just the filename, no path).

    Returns:
        Confirmation message with the local path.
    """
    sandbox = _get_sandbox()
    content = sandbox.files.read_bytes(sandbox_path)
    FILES_OUT_DIR.mkdir(parents=True, exist_ok=True)
    local_path = FILES_OUT_DIR / filename
    local_path.write_bytes(content)
    return f"Exported {sandbox_path} -> {local_path}"


def import_to_sandbox(filename: str, sandbox_path: str) -> str:
    """Copy a file from the local /files/in/ directory into the sandbox.

    Use this to make input files available inside the sandbox for processing.

    Args:
        filename: Name of the file in the local /files/in/ directory.
        sandbox_path: Absolute path where the file should be placed in the sandbox.

    Returns:
        Confirmation message.
    """
    local_path = FILES_IN_DIR / filename
    if not local_path.exists():
        return f"Error: File not found: {local_path}"
    content = local_path.read_bytes()
    sandbox = _get_sandbox()
    sandbox.files.write_file(sandbox_path, content)
    return f"Imported {local_path} -> {sandbox_path}"
