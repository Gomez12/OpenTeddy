"""
OpenAI-compatible embedding server using sentence-transformers.

Serves POST /v1/embeddings with the same interface as OpenAI's API,
so any client that speaks OpenAI embeddings can use this server.

Usage:
    uvicorn agentic.servers.embedding_server:app --host 0.0.0.0 --port 8100
"""

import os
import time
from pathlib import Path

import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_embed_model_env = os.environ.get("EMBED_MODEL", "intfloat/multilingual-e5-base")
_embed_model_path = _PROJECT_ROOT / _embed_model_env
EMBED_MODEL = str(_embed_model_path) if _embed_model_path.is_dir() else _embed_model_env

app = FastAPI(title="Embedding Server", version="1.0.0")

_model = None


def _get_model():
    global _model
    if _model is None:
        import platform
        import torch
        from sentence_transformers import SentenceTransformer

        device = (
            "mps" if platform.system() == "Darwin" and torch.backends.mps.is_available()
            else "cuda" if torch.cuda.is_available()
            else "cpu"
        )
        print(f"Loading embedding model {EMBED_MODEL} on {device}...")
        _model = SentenceTransformer(EMBED_MODEL, device=device)
        print("Embedding model loaded.")
    return _model


class EmbeddingRequest(BaseModel):
    input: str | list[str]
    model: str = "multilingual-e5-base"
    encoding_format: str = "float"


class EmbeddingData(BaseModel):
    object: str = "embedding"
    embedding: list[float]
    index: int


class UsageInfo(BaseModel):
    prompt_tokens: int
    total_tokens: int


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: list[EmbeddingData]
    model: str
    usage: UsageInfo


@app.post("/v1/embeddings")
def create_embeddings(request: EmbeddingRequest) -> EmbeddingResponse:
    model = _get_model()

    texts = [request.input] if isinstance(request.input, str) else request.input
    embeddings = model.encode(texts, normalize_embeddings=True)

    data = [
        EmbeddingData(embedding=emb.tolist(), index=i)
        for i, emb in enumerate(embeddings)
    ]

    total_tokens = sum(len(t.split()) for t in texts)

    return EmbeddingResponse(
        data=data,
        model=request.model,
        usage=UsageInfo(prompt_tokens=total_tokens, total_tokens=total_tokens),
    )


@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "multilingual-e5-base",
                "object": "model",
                "owned_by": "intfloat",
            }
        ],
    }


@app.get("/health")
def health():
    return {"status": "ok"}
