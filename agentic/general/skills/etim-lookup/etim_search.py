"""
ETIM semantic search tool.

Searches the LanceDB with ETIM groups and classes using vector similarity
to find the best matching group or class code for a product description.

Uses an OpenAI-compatible embedding server (EMBED_API_BASE) when available,
falls back to loading the model locally.
"""

import json
import os
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

import lancedb

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
LANCEDB_PATH = _PROJECT_ROOT / "agentic" / "general" / "lancedbs" / "etimdynamic"
EMBED_API_BASE = os.environ.get("EMBED_API_BASE", "")
EMBED_MODEL_NAME = os.environ.get("EMBED_MODEL_NAME", "multilingual-e5-base")

_local_model = None
_db: lancedb.DBConnection | None = None


def _embed_via_api(text: str) -> list[float]:
    """Get embedding from the OpenAI-compatible embedding server."""
    url = f"{EMBED_API_BASE}/v1/embeddings"
    payload = json.dumps({"input": text, "model": EMBED_MODEL_NAME}).encode()
    req = Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urlopen(req) as resp:
        data = json.loads(resp.read())
    return data["data"][0]["embedding"]


def _embed_local(text: str) -> list[float]:
    """Get embedding using a locally loaded model."""
    global _local_model
    if _local_model is None:
        import platform
        import torch
        from sentence_transformers import SentenceTransformer

        _embed_model_env = os.environ.get("EMBED_MODEL", "intfloat/multilingual-e5-base")
        _embed_model_path = _PROJECT_ROOT / _embed_model_env
        model_path = str(_embed_model_path) if _embed_model_path.is_dir() else _embed_model_env

        device = (
            "mps" if platform.system() == "Darwin" and torch.backends.mps.is_available()
            else "cuda" if torch.cuda.is_available()
            else "cpu"
        )
        _local_model = SentenceTransformer(model_path, device=device)
    return _local_model.encode(text, normalize_embeddings=True).tolist()


def _embed(text: str) -> list[float]:
    """Get embedding vector, preferring API server, falling back to local model."""
    if EMBED_API_BASE:
        try:
            return _embed_via_api(text)
        except (URLError, OSError):
            pass  # Fall through to local
    return _embed_local(text)


def _get_db() -> lancedb.DBConnection:
    global _db
    if _db is None:
        _db = lancedb.connect(str(LANCEDB_PATH))
    return _db


def search_etim_groups(query: str, top_k: int = 50) -> str:
    """Search for the best matching ETIM group(s) given a product description.

    Args:
        query: Product description or search terms (Dutch or English).
        top_k: Number of results to return (default 50).

    Returns:
        Formatted string with matching ETIM groups, their codes, and descriptions.
    """
    db = _get_db()
    table = db.open_table("etim_groups")
    vec = _embed(query)
    results = table.search(vec).limit(top_k).to_pandas()

    lines = []
    for _, row in results.iterrows():
        dist = row.get("_distance", "?")
        lines.append(
            f"- {row['group_code']}: {row['description_en']} / {row['description_nl']} "
            f"(distance: {dist:.4f})"
        )
    return f"Top {top_k} ETIM groups for '{query}':\n" + "\n".join(lines)


def search_etim_classes(query: str, top_k: int = 50) -> str:
    """Search for the best matching ETIM class(es) given a product description.

    Args:
        query: Product description or search terms (Dutch or English).
        top_k: Number of results to return (default 50).

    Returns:
        Formatted string with matching ETIM classes, their codes, group codes,
        descriptions, synonyms, and relevant features.
    """
    db = _get_db()
    table = db.open_table("etim_classes")
    vec = _embed(query)
    results = table.search(vec).limit(top_k).to_pandas()

    lines = []
    for _, row in results.iterrows():
        dist = row.get("_distance", "?")
        syns = row.get("synonyms_en", "")
        syns_nl = row.get("synonyms_nl", "")
        feats = row.get("features_text", "")
        entry = (
            f"- {row['class_code']} (group: {row['group_code']}): "
            f"{row['description_en']} / {row['description_nl']} "
            f"(distance: {dist:.4f})"
        )
        if syns:
            entry += f"\n  Synonyms EN: {syns}"
        if syns_nl:
            entry += f"\n  Synonyms NL: {syns_nl}"
        if feats:
            entry += f"\n  Features: {feats[:200]}"
        lines.append(entry)
    return f"Top {top_k} ETIM classes for '{query}':\n" + "\n".join(lines)
