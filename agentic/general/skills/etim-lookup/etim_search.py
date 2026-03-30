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
_api_available: bool | None = None  # None = not tested yet


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
    global _api_available
    if EMBED_API_BASE and _api_available is not False:
        try:
            result = _embed_via_api(text)
            _api_available = True
            return result
        except (URLError, OSError):
            _api_available = False
    return _embed_local(text)


def _get_db() -> lancedb.DBConnection:
    global _db
    if _db is None:
        _db = lancedb.connect(str(LANCEDB_PATH))
    return _db


_tables: dict[str, object] = {}


def _get_table(name: str):
    if name not in _tables:
        _tables[name] = _get_db().open_table(name)
    return _tables[name]


def search_etim_groups(query: str, top_k: int = 50) -> str:
    """Search for the best matching ETIM group(s) given a product description.

    Args:
        query: Product description or search terms (Dutch or English).
        top_k: Number of results to return (default 50).

    Returns:
        Formatted string with matching ETIM groups, their codes, and descriptions.
    """
    table = _get_table("etim_groups")
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
    table = _get_table("etim_classes")
    vec = _embed(query)
    results = table.search(vec).limit(top_k).to_pandas()

    lines = []
    for i, (_, row) in enumerate(results.iterrows()):
        dist = row.get("_distance", "?")
        entry = (
            f"- {row['class_code']} ({row['group_code']}): "
            f"{row['description_en']} / {row['description_nl']} "
            f"(d:{dist:.4f})"
        )
        # Only include details for top 10 to keep output manageable
        if i < 10:
            syns = row.get("synonyms_en", "")
            syns_nl = row.get("synonyms_nl", "")
            feats = row.get("features_text", "")
            if syns:
                entry += f"\n  syn-en: {syns[:120]}"
            if syns_nl:
                entry += f"\n  syn-nl: {syns_nl[:120]}"
            if feats:
                entry += f"\n  feat: {feats[:120]}"
        lines.append(entry)
    return f"Top {top_k} ETIM classes for '{query}':\n" + "\n".join(lines)


def get_class_features(class_code: str) -> str:
    """Get the full feature list for a specific ETIM class, including feature codes, types, and units.

    Use this to retrieve the complete feature template for a class when you need to
    fill in an ETIM card with values. Returns structured feature data with codes,
    descriptions (EN/NL), value types, and unit abbreviations.

    Args:
        class_code: The ETIM class code (e.g. EC001959).

    Returns:
        JSON string with class info and all features, or an error message.
    """
    import json as _json

    table = _get_table("etim_classes")
    results = table.search().where(f"class_code = '{class_code}'").limit(1).to_pandas()

    if results.empty:
        return f"Class {class_code} not found."

    row = results.iloc[0]
    features_raw = row.get("features_json", "[]")
    try:
        features = _json.loads(features_raw)
    except (TypeError, _json.JSONDecodeError):
        features = []

    result = {
        "class_code": row["class_code"],
        "group_code": row["group_code"],
        "description_en": row["description_en"],
        "description_nl": row["description_nl"],
        "synonyms_en": row.get("synonyms_en", ""),
        "synonyms_nl": row.get("synonyms_nl", ""),
        "features": features,
    }
    return _json.dumps(result, ensure_ascii=False, indent=2)
