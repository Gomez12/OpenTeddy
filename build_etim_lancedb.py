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

import os
import platform
import sys
import zipfile
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree.ElementTree import iterparse

import httpx
import lancedb
import torch
from sentence_transformers import SentenceTransformer

# ── Config ──────────────────────────────────────────────────────────────────
LANCEDB_PATH = Path(__file__).parent / "agentic" / "general" / "lancedbs" / "etimdynamic"
CDN_URL = "https://cdn.etim-international.com/exports/ETIMIXF3_1_{date}.zip"
NS = "https://www.etim-international.com/etimixf/31"
EMBED_MODEL = os.environ.get("EMBED_MODEL", "intfloat/multilingual-e5-base")


def _detect_device() -> tuple[str, int]:
    """Pick the best available device and a matching batch size."""
    if platform.system() == "Darwin" and torch.backends.mps.is_available():
        return "mps", 64
    if torch.cuda.is_available():
        return "cuda", 64
    return "cpu", 8


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
def parse_features_lookup(xml_path: str) -> dict[str, str]:
    """Build a dict of feature_code -> EN description for enriching classes."""
    features = {}
    for event, elem in iterparse(xml_path, events=("end",)):
        if elem.tag == tag("Feature") and elem.find(tag("Code")) is not None:
            code_el = elem.find(tag("Code"))
            if code_el is not None and code_el.text and code_el.text.startswith("EF"):
                desc_en, _ = get_translation(elem.find(tag("Translations")), "EN")
                if desc_en:
                    features[code_el.text] = desc_en
            elem.clear()
    return features


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


def parse_classes(xml_path: str, feature_lookup: dict[str, str]) -> list[dict]:
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

        # Collect feature descriptions for this class
        features_el = elem.find(tag("Features"))
        feature_descs = []
        if features_el is not None:
            for feat in features_el:
                fc_el = feat.find(tag("FeatureCode"))
                if fc_el is not None and fc_el.text and fc_el.text in feature_lookup:
                    feature_descs.append(feature_lookup[fc_el.text])

        features_text = ", ".join(feature_descs[:30])  # cap to keep embedding text reasonable
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
            "search_text": search_text,
        })
        elem.clear()
    return rows


# ── Embedding ───────────────────────────────────────────────────────────────
def get_embeddings(texts: list[str], model: SentenceTransformer, batch_size: int) -> list[list[float]]:
    """Generate embeddings locally with sentence-transformers."""
    print(f"  Encoding {len(texts)} texts (batch_size={batch_size}) ...")
    vectors = model.encode(texts, batch_size=batch_size, show_progress_bar=True, normalize_embeddings=True)
    return vectors.tolist()


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    date_or_path = sys.argv[1] if len(sys.argv) > 1 else None
    xml_path = download_xml(date_or_path)

    device, batch_size = _detect_device()
    print(f"Device: {device} | batch_size: {batch_size}")
    print(f"Loading embedding model: {EMBED_MODEL} ...")
    model = SentenceTransformer(EMBED_MODEL, device=device)

    # 1. Parse features lookup (need two passes since features come before classes)
    print("Parsing features ...")
    feature_lookup = parse_features_lookup(xml_path)
    print(f"  {len(feature_lookup)} features loaded")

    # 2. Parse groups
    print("Parsing groups ...")
    groups = parse_groups(xml_path)
    print(f"  {len(groups)} groups")

    # 3. Parse classes
    print("Parsing classes ...")
    classes = parse_classes(xml_path, feature_lookup)
    print(f"  {len(classes)} classes")

    # 4. Generate embeddings
    print("Generating embeddings for groups ...")
    group_vectors = get_embeddings([g["search_text"] for g in groups], model, batch_size)
    for g, vec in zip(groups, group_vectors):
        g["vector"] = vec

    print("Generating embeddings for classes ...")
    class_vectors = get_embeddings([c["search_text"] for c in classes], model, batch_size)
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
