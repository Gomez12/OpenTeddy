"""
Chat API server for the OpenTeddy agent.

Provides a REST endpoint for the frontend to communicate with agent.py.
Uses the username as thread_id for conversation persistence.
"""

import sys
from pathlib import Path

# Ensure agentic/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from baseagent import create_agent, _get_callbacks, _flush_callbacks

app = FastAPI(title="OpenTeddy Chat", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        _agent = create_agent(
            system_prompt=(
                "You are a helpful assistant that specialises in ETIM product classification.\n"
                "For ETIM classification: ALWAYS read and follow the etim-lookup skill before using search tools.\n"
                "The skill contains the required search strategy (minimum number of searches, output format, etc.)."
            ),
        )
    return _agent


class ChatRequest(BaseModel):
    message: str
    username: str


class ChatResponse(BaseModel):
    response: str
    username: str


@app.post("/api/chat")
def chat(req: ChatRequest) -> ChatResponse:
    agent = _get_agent()
    callbacks = _get_callbacks()
    result = agent.invoke(
        {"messages": [{"role": "user", "content": req.message}]},
        config={"configurable": {"thread_id": req.username}, "callbacks": callbacks},
    )
    _flush_callbacks(callbacks)
    content = result["messages"][-1].content
    if isinstance(content, list):
        text = "\n".join(block["text"] for block in content if block.get("type") == "text")
    else:
        text = content
    return ChatResponse(response=text, username=req.username)


@app.get("/health")
def health():
    return {"status": "ok"}
