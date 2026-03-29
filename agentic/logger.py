"""
JSONL logger for all LLM communication.

Logs every request to and response from the LLM, including tool calls,
to timestamped JSONL files in the agentic/logs/ directory.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage

LOGS_DIR = Path(__file__).resolve().parent / "logs"


def _serialize(obj):
    """Make objects JSON-serializable."""
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, BaseMessage):
        return {"type": obj.type, "content": obj.content, "additional_kwargs": obj.additional_kwargs}
    if isinstance(obj, BaseException):
        return {"error": type(obj).__name__, "message": str(obj)}
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    return str(obj)


class LLMLogger(BaseCallbackHandler):
    """Callback handler that logs all LLM communication to JSONL files."""

    def __init__(self):
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = LOGS_DIR / f"llm_{timestamp}.jsonl"
        self._file = open(log_path, "a", encoding="utf-8")

    def __del__(self):
        if hasattr(self, "_file") and not self._file.closed:
            self._file.close()

    def _write(self, entry: dict):
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        self._file.write(json.dumps(entry, default=_serialize, ensure_ascii=False) + "\n")
        self._file.flush()

    def on_llm_start(self, serialized, prompts, *, run_id, parent_run_id=None, **kwargs):
        self._write({
            "event": "llm_start",
            "run_id": run_id,
            "parent_run_id": parent_run_id,
            "model": serialized.get("id", []),
            "model_name": serialized.get("name"),
            "prompts": prompts,
            "kwargs": {k: v for k, v in kwargs.items() if k in ("invocation_params", "tags", "metadata")},
        })

    def on_chat_model_start(self, serialized, messages, *, run_id, parent_run_id=None, **kwargs):
        self._write({
            "event": "chat_model_start",
            "run_id": run_id,
            "parent_run_id": parent_run_id,
            "model": serialized.get("id", []),
            "model_name": serialized.get("name"),
            "messages": [[_serialize(m) for m in batch] for batch in messages],
            "kwargs": {k: v for k, v in kwargs.items() if k in ("invocation_params", "tags", "metadata")},
        })

    def on_llm_end(self, response, *, run_id, parent_run_id=None, **kwargs):
        generations = []
        for gen_list in response.generations:
            for gen in gen_list:
                entry = {"text": gen.text, "generation_info": gen.generation_info}
                if hasattr(gen, "message"):
                    entry["message"] = _serialize(gen.message)
                generations.append(entry)

        self._write({
            "event": "llm_end",
            "run_id": run_id,
            "parent_run_id": parent_run_id,
            "generations": generations,
            "llm_output": response.llm_output,
        })

    def on_llm_error(self, error, *, run_id, parent_run_id=None, **kwargs):
        self._write({
            "event": "llm_error",
            "run_id": run_id,
            "parent_run_id": parent_run_id,
            "error": _serialize(error),
        })

    def on_tool_start(self, serialized, input_str, *, run_id, parent_run_id=None, **kwargs):
        self._write({
            "event": "tool_start",
            "run_id": run_id,
            "parent_run_id": parent_run_id,
            "tool_name": serialized.get("name"),
            "input": input_str,
        })

    def on_tool_end(self, output, *, run_id, parent_run_id=None, **kwargs):
        self._write({
            "event": "tool_end",
            "run_id": run_id,
            "parent_run_id": parent_run_id,
            "output": str(output)[:5000],
        })

    def on_tool_error(self, error, *, run_id, parent_run_id=None, **kwargs):
        self._write({
            "event": "tool_error",
            "run_id": run_id,
            "parent_run_id": parent_run_id,
            "error": _serialize(error),
        })

    def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, **kwargs):
        self._write({
            "event": "chain_start",
            "run_id": run_id,
            "parent_run_id": parent_run_id,
            "chain_name": (serialized or {}).get("name"),
            "chain_id": (serialized or {}).get("id", []),
        })

    def on_chain_end(self, outputs, *, run_id, parent_run_id=None, **kwargs):
        self._write({
            "event": "chain_end",
            "run_id": run_id,
            "parent_run_id": parent_run_id,
        })

    def on_chain_error(self, error, *, run_id, parent_run_id=None, **kwargs):
        self._write({
            "event": "chain_error",
            "run_id": run_id,
            "parent_run_id": parent_run_id,
            "error": _serialize(error),
        })
