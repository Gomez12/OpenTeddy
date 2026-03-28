"""
Read-only wrapper for any BackendProtocol.

Allows read operations (ls, read, grep, glob, download) but blocks
all write operations (write, edit, upload) with a permission_denied error.
"""

from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    WriteResult,
)


class ReadOnlyBackend(BackendProtocol):
    """Wraps a backend to make it read-only."""

    def __init__(self, inner: BackendProtocol):
        self._inner = inner

    # -- Read operations: delegate to inner --

    def ls_info(self, path: str) -> list[FileInfo]:
        return self._inner.ls_info(path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        return self._inner.read(file_path, offset, limit)

    def grep_raw(self, pattern: str, path: str | None = None, glob: str | None = None) -> list[GrepMatch] | str:
        return self._inner.grep_raw(pattern, path, glob)

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        return self._inner.glob_info(pattern, path)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return self._inner.download_files(paths)

    # -- Write operations: blocked --

    def write(self, file_path: str, content: str) -> WriteResult:
        return WriteResult(error="Permission denied: this directory is read-only")

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        return EditResult(error="Permission denied: this directory is read-only")

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=p, error="permission_denied") for p, _ in files]
