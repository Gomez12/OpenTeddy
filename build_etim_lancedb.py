"""
Download the ETIM dynamic release (ETIMIXF 3.1) and build a LanceDB
for semantic search on groups and classes.

Tables created:
  - etim_groups  : group_code, description_en, description_nl, search_text
  - etim_classes : class_code, group_code, description_en, description_nl,
                   synonyms_en, synonyms_nl, features_text, search_text

The `search_text` column is embedded locally using sentence-transformers
so you can do vector search for the best matching group or class given
a product description.

Usage:
    python build_etim_lancedb.py              # auto-downloads yesterday's export
    python build_etim_lancedb.py 20260320     # use a specific date
    python build_etim_lancedb.py /path/to.xml # use a local XML file
"""

import json
import os
import platform
import sys
import zipfile
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError
from xml.etree.ElementTree import iterparse

import httpx
import lancedb

from dotenv import load_dotenv

load_dotenv()

# ── Config ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
LANCEDB_PATH = PROJECT_ROOT / "agentic" / "general" / "lancedbs" / "etimdynamic"
CDN_URL = "https://cdn.etim-international.com/exports/ETIMIXF3_1_{date}.zip"
NS = "https://www.etim-international.com/etimixf/31"
EMBED_API_BASE = os.environ.get("EMBED_API_BASE", "")
EMBED_MODEL_NAME = os.environ.get("EMBED_MODEL_NAME", "multilingual-e5-base")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "intfloat/multilingual-e5-base")

_local_model = None


def _detect_device() -> tuple[str, int]:
    """Pick the best available device and a matching batch size."""
    import torch

    if platform.system() == "Darwin" and torch.backends.mps.is_available():
        return "mps", 64
    if torch.cuda.is_available():
        return "cuda", 64
    return "cpu", 8


def _embed_batch_via_api(texts: list[str]) -> list[list[float]]:
    """Get embeddings from the OpenAI-compatible embedding server."""
    url = f"{EMBED_API_BASE}/v1/embeddings"
    payload = json.dumps({"input": texts, "model": EMBED_MODEL_NAME}).encode()
    req = Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    # Sort by index to ensure correct order
    sorted_data = sorted(data["data"], key=lambda x: x["index"])
    return [d["embedding"] for d in sorted_data]


def _get_local_model():
    """Load the local sentence-transformers model (lazy)."""
    global _local_model
    if _local_model is None:
        import torch
        from sentence_transformers import SentenceTransformer

        _embed_model_path = PROJECT_ROOT / EMBED_MODEL
        model_path = str(_embed_model_path) if _embed_model_path.is_dir() else EMBED_MODEL

        device, _ = _detect_device()
        print(f"Loading local embedding model: {model_path} on {device} ...")
        _local_model = SentenceTransformer(model_path, device=device)
    return _local_model


# ── Helpers ─────────────────────────────────────────────────────────────────
def tag(name: str) -> str:
    return f"{{{NS}}}{name}"


def get_translation(translations_el, lang: str) -> tuple[str, list[str]]:
    """Return (description, [synonyms]) for a given language from a Translations element."""
    if translations_el is None:
        return "", []
    for tr in translations_el:
        if tr.get("language") == lang:
            desc_el = tr.find(tag("Description"))
            desc = desc_el.text if desc_el is not None and desc_el.text else ""
            syns = [s.text for s in tr.findall(f"{tag('Synonyms')}/{tag('Synonym')}") if s.text]
            return desc, syns
    return "", []


def download_xml(date_str: str | None) -> str:
    """Download ETIMIXF zip from CDN, extract XML, return path to extracted file."""
    if date_str and os.path.isfile(date_str):
        print(f"Using local file: {date_str}")
        return date_str

    if not date_str:
        date_str = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

    url = CDN_URL.format(date=date_str)
    print(f"Downloading {url} ...")
    resp = httpx.get(url, follow_redirects=True, timeout=120)
    resp.raise_for_status()

    tmp_dir = tempfile.mkdtemp(prefix="etim_")
    zip_path = os.path.join(tmp_dir, "etim.zip")
    with open(zip_path, "wb") as f:
        f.write(resp.content)

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        xml_name = [n for n in names if n.endswith(".xml")][0]
        zf.extract(xml_name, tmp_dir)
        xml_path = os.path.join(tmp_dir, xml_name)

    print(f"Extracted: {xml_path}")
    return xml_path


# ── XML parsing ─────────────────────────────────────────────────────────────
def get_abbreviation(translations_el, lang: str) -> str:
    """Return the unit abbreviation for a language."""
    if translations_el is None:
        return ""
    for tr in translations_el:
        if tr.get("language") == lang:
            abbr_el = tr.find(tag("Abbreviation"))
            return abbr_el.text if abbr_el is not None and abbr_el.text else ""
    return ""


def parse_features_lookup(xml_path: str) -> dict[str, dict]:
    """Build a dict of feature_code -> {code, type, en, nl} for enriching classes."""
    features = {}
    for event, elem in iterparse(xml_path, events=("end",)):
        if elem.tag == tag("Feature") and elem.find(tag("Code")) is not None:
            code_el = elem.find(tag("Code"))
            if code_el is not None and code_el.text and code_el.text.startswith("EF"):
                type_el = elem.find(tag("Type"))
                desc_en, _ = get_translation(elem.find(tag("Translations")), "EN")
                desc_nl, _ = get_translation(elem.find(tag("Translations")), "nl-BE")
                if desc_en or desc_nl:
                    features[code_el.text] = {
                        "code": code_el.text,
                        "type": type_el.text if type_el is not None else "",
                        "en": desc_en,
                        "nl": desc_nl or desc_en,
                    }
            elem.clear()
    return features


def parse_units_lookup(xml_path: str) -> dict[str, dict]:
    """Build a dict of unit_code -> {code, en, nl, abbr}."""
    units = {}
    for event, elem in iterparse(xml_path, events=("end",)):
        if elem.tag == tag("Unit") and elem.find(tag("Code")) is not None:
            code_el = elem.find(tag("Code"))
            if code_el is not None and code_el.text and code_el.text.startswith("EU"):
                translations = elem.find(tag("Translations"))
                desc_en, _ = get_translation(translations, "EN")
                desc_nl, _ = get_translation(translations, "nl-BE")
                abbr = get_abbreviation(translations, "EN")
                units[code_el.text] = {
                    "code": code_el.text,
                    "en": desc_en,
                    "nl": desc_nl or desc_en,
                    "abbr": abbr,
                }
            elem.clear()
    return units


def parse_values_lookup(xml_path: str) -> dict[str, dict]:
    """Build a dict of value_code -> {code, en, nl}."""
    values = {}
    for event, elem in iterparse(xml_path, events=("end",)):
        if elem.tag == tag("Value") and elem.find(tag("Code")) is not None:
            code_el = elem.find(tag("Code"))
            if code_el is not None and code_el.text and code_el.text.startswith("EV"):
                translations = elem.find(tag("Translations"))
                desc_en, _ = get_translation(translations, "EN")
                desc_nl, _ = get_translation(translations, "nl-BE")
                values[code_el.text] = {
                    "code": code_el.text,
                    "en": desc_en,
                    "nl": desc_nl or desc_en,
                }
            elem.clear()
    return values


def parse_groups(xml_path: str) -> list[dict]:
    rows = []
    for event, elem in iterparse(xml_path, events=("end",)):
        if elem.tag == tag("Group"):
            code_el = elem.find(tag("Code"))
            if code_el is None or not code_el.text:
                elem.clear()
                continue
            code = code_el.text
            translations = elem.find(tag("Translations"))
            desc_en, _ = get_translation(translations, "EN")
            desc_nl, _ = get_translation(translations, "nl-BE")
            search_text = f"{code} | {desc_en} | {desc_nl}".strip(" |")
            rows.append({
                "group_code": code,
                "description_en": desc_en,
                "description_nl": desc_nl,
                "search_text": search_text,
            })
            elem.clear()
    return rows


def parse_classes(xml_path: str, feature_lookup: dict[str, dict], unit_lookup: dict[str, dict], value_lookup: dict[str, dict]) -> list[dict]:
    rows = []
    for event, elem in iterparse(xml_path, events=("end",)):
        if elem.tag != tag("Class"):
            continue
        code_el = elem.find(tag("Code"))
        if code_el is None or not code_el.text:
            elem.clear()
            continue

        code = code_el.text
        group_code_el = elem.find(tag("GroupCode"))
        group_code = group_code_el.text if group_code_el is not None and group_code_el.text else ""

        translations = elem.find(tag("Translations"))
        desc_en, syns_en = get_translation(translations, "EN")
        desc_nl, syns_nl = get_translation(translations, "nl-BE")

        # Collect structured feature data for this class
        features_el = elem.find(tag("Features"))
        features_json = []
        feature_descs = []
        if features_el is not None:
            for feat in sorted(features_el, key=lambda f: int(f.findtext(tag("OrderNumber")) or "999")):
                fc_el = feat.find(tag("FeatureCode"))
                if fc_el is None or not fc_el.text or fc_el.text not in feature_lookup:
                    continue
                # Skip features marked for deletion
                if "deleted" in (feat.get("changeCode") or "").lower():
                    continue
                f_info = feature_lookup[fc_el.text]
                uc_el = feat.find(tag("UnitCode"))
                unit = unit_lookup.get(uc_el.text, {}) if uc_el is not None and uc_el.text else {}

                # Collect allowed values (EV codes) for this class-feature
                allowed_values = []
                values_el = feat.find(tag("Values"))
                if values_el is not None:
                    for val in sorted(values_el, key=lambda v: int(v.findtext(tag("OrderNumber")) or "999")):
                        vc_el = val.find(tag("ValueCode"))
                        if vc_el is not None and vc_el.text and vc_el.text in value_lookup:
                            allowed_values.append(value_lookup[vc_el.text])

                feat_entry = {
                    "code": f_info["code"],
                    "type": f_info["type"],
                    "en": f_info["en"],
                    "nl": f_info["nl"],
                    "unit": unit.get("abbr", ""),
                }
                if allowed_values:
                    feat_entry["allowed_values"] = allowed_values
                features_json.append(feat_entry)
                feature_descs.append(f_info["en"])

        import json
        features_text = ", ".join(feature_descs[:30])
        synonyms_en = ", ".join(syns_en)
        synonyms_nl = ", ".join(syns_nl)

        search_text = " | ".join(filter(None, [
            code, desc_en, desc_nl, synonyms_en, synonyms_nl, features_text
        ]))

        rows.append({
            "class_code": code,
            "group_code": group_code,
            "description_en": desc_en,
            "description_nl": desc_nl,
            "synonyms_en": synonyms_en,
            "synonyms_nl": synonyms_nl,
            "features_text": features_text,
            "features_json": json.dumps(features_json, ensure_ascii=False),
            "search_text": search_text,
        })
        elem.clear()
    return rows


# ── Embedding ───────────────────────────────────────────────────────────────
def _check_api_available() -> bool:
    """Test if the embedding API server is reachable."""
    if not EMBED_API_BASE:
        return False
    try:
        _embed_batch_via_api(["test"])
        print(f"  Embedding API available at {EMBED_API_BASE}")
        return True
    except (URLError, OSError) as e:
        print(f"  Embedding API not available ({e}), using local model")
        return False


def get_embeddings(texts: list[str], batch_size: int, use_api: bool) -> list[list[float]]:
    """Generate embeddings via API server or local model."""
    print(f"  Encoding {len(texts)} texts (batch_size={batch_size}) ...")

    if use_api:
        all_vectors = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            vectors = _embed_batch_via_api(batch)
            all_vectors.extend(vectors)
            if (i // batch_size) % 10 == 0:
                print(f"    {i + len(batch)}/{len(texts)}")
        return all_vectors

    model = _get_local_model()
    vectors = model.encode(texts, batch_size=batch_size, show_progress_bar=True, normalize_embeddings=True)
    return vectors.tolist()


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    date_or_path = sys.argv[1] if len(sys.argv) > 1 else None
    xml_path = download_xml(date_or_path)

    _, batch_size = _detect_device()
    use_api = _check_api_available()

    print("Parsing features ...")
    feature_lookup = parse_features_lookup(xml_path)
    print(f"  {len(feature_lookup)} features loaded")

    print("Parsing units ...")
    unit_lookup = parse_units_lookup(xml_path)
    print(f"  {len(unit_lookup)} units loaded")

    print("Parsing values ...")
    value_lookup = parse_values_lookup(xml_path)
    print(f"  {len(value_lookup)} values loaded")

    print("Parsing groups ...")
    groups = parse_groups(xml_path)
    print(f"  {len(groups)} groups")

    print("Parsing classes ...")
    classes = parse_classes(xml_path, feature_lookup, unit_lookup, value_lookup)
    print(f"  {len(classes)} classes")

    print("Generating embeddings for groups ...")
    group_vectors = get_embeddings([g["search_text"] for g in groups], batch_size, use_api)
    for g, vec in zip(groups, group_vectors):
        g["vector"] = vec

    print("Generating embeddings for classes ...")
    class_vectors = get_embeddings([c["search_text"] for c in classes], batch_size, use_api)
    for c, vec in zip(classes, class_vectors):
        c["vector"] = vec

    # 5. Write to LanceDB
    LANCEDB_PATH.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(LANCEDB_PATH))

    resp = db.list_tables()
    existing = set(resp.tables) if hasattr(resp, "tables") else set(resp)

    print("Writing etim_groups table ...")
    if "etim_groups" in existing:
        db.drop_table("etim_groups")
    db.create_table("etim_groups", groups)

    print("Writing etim_classes table ...")
    if "etim_classes" in existing:
        db.drop_table("etim_classes")
    db.create_table("etim_classes", classes)

    print(f"\nDone! LanceDB at: {LANCEDB_PATH}")
    print(f"  etim_groups : {len(groups)} rows")
    print(f"  etim_classes: {len(classes)} rows")


if __name__ == "__main__":
    main()
