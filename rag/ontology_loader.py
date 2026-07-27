"""
rag/ontology_loader.py — Download + parse CL, UBERON, EFO ontologies.

Ontology sizes (approximate term counts after filtering obsolete):
    CL     (Cell Ontology)              ~  4,500 terms   fast
    UBERON (Ubiquitous Anatomy)         ~ 15,000 terms   medium
    EFO    (Experimental Factor Ont.)   ~ 30,000 terms   slow

Total: ~50,000 terms → embedding takes ~10–15 min on an 8 GB VRAM GPU (first run only).
The index is then cached in ./data/vector_store/ and loads in <1 s thereafter.

File format: OBO (Open Biomedical Ontologies) — plain-text, human-readable.
Docs: https://owlcollab.github.io/oboformat/doc/obo-syntax.html
"""

import requests
from pathlib import Path
from typing import Iterator

from config import settings

# ── Ontology source URLs ──────────────────────────────────────────────────────
# Using *-basic.obo where available — strips complex OWL axioms, much smaller.

ONTOLOGY_SOURCES: dict[str, str] = {
    "CL": (
        "https://github.com/obophenotype/cell-ontology"
        "/releases/latest/download/cl-basic.obo"
    ),
    "UBERON": (
        "https://github.com/obophenotype/uberon"
        "/releases/latest/download/uberon-basic.obo"
    ),
    "EFO": (
        "https://github.com/EBISPOT/efo"
        "/releases/latest/download/efo.obo"
    ),
}


# ── Download ──────────────────────────────────────────────────────────────────

def download_ontology(name: str, url: str, dest_dir: Path) -> Path:
    """
    Download an OBO file from `url` into `dest_dir` if not already cached.
    Shows a progress bar.
    """
    dest = dest_dir / f"{name.lower()}.obo"
    if dest.exists():
        size_mb = dest.stat().st_size / 1_048_576
        print(f"  [{name}] Cached ({size_mb:.1f} MB) — skipping download")
        return dest

    print(f"  [{name}] Downloading from {url} ...")
    dest_dir.mkdir(parents=True, exist_ok=True)

    with requests.get(url, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0

        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65_536):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    print(f"  [{name}] {pct:5.1f}%", end="\r", flush=True)

    size_mb = dest.stat().st_size / 1_048_576
    print(f"  [{name}] Done — {size_mb:.1f} MB saved to {dest}")
    return dest


# ── OBO Parser ────────────────────────────────────────────────────────────────

def _parse_obo(filepath: Path) -> Iterator[dict]:
    """
    Stream-parse an OBO file into term dicts.

    Yielded dict fields:
        id          e.g. "CL:0000583"
        name        e.g. "alveolar macrophage"
        definition  prose text (optional)
        synonyms    list of alternate label strings
        namespace   e.g. "cell"
        obsolete    True if tagged is_obsolete: true
    """
    current: dict = {}
    in_term = False

    with open(filepath, encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()

            # ── Section header ────────────────────────────────────────────────
            if line == "[Term]":
                if current and "id" in current:
                    yield current
                current = {}
                in_term = True
                continue

            if line.startswith("[") and line != "[Term]":
                if current and "id" in current:
                    yield current
                current = {}
                in_term = False
                continue

            if not in_term or not line or ": " not in line:
                continue

            # ── Field parsing ─────────────────────────────────────────────────
            key, _, value = line.partition(": ")
            key   = key.strip()
            value = value.strip()

            if key == "id":
                current["id"] = value

            elif key == "name":
                current["name"] = value

            elif key == "def":
                # Format:  def: "Description text." [refs]
                current["definition"] = (
                    value.split('"')[1] if '"' in value else value
                )

            elif key == "synonym":
                # Format:  synonym: "alt name" EXACT []
                syn_list = current.setdefault("synonyms", [])
                if '"' in value:
                    syn_text = value.split('"')[1].strip()
                    if syn_text:
                        syn_list.append(syn_text)

            elif key == "is_obsolete" and value == "true":
                current["obsolete"] = True

            elif key == "namespace":
                current["namespace"] = value

    # yield last term
    if current and "id" in current:
        yield current


# ── Public loader ─────────────────────────────────────────────────────────────

def load_all_ontologies(data_dir: Path | None = None) -> list[dict]:
    """
    Download (if needed) and parse all three ontologies.

    Returns a list of term dicts, each enriched with:
        ontology    source ontology key ("CL", "UBERON", "EFO")
        embed_text  concatenated text that will be embedded:
                    "name | definition | synonym1 | synonym2 | synonym3"
    """
    if data_dir is None:
        data_dir = Path(settings.ONTOLOGY_DATA_PATH)

    all_terms: list[dict] = []

    for name, url in ONTOLOGY_SOURCES.items():
        obo_path = download_ontology(name, url, data_dir)
        count = 0

        for term in _parse_obo(obo_path):
            # Skip obsolete and terms without a name.
            if term.get("obsolete") or not term.get("name"):
                continue

            # Build embed_text — this is what the embedding model sees.
            parts = [term["name"]]
            if "definition" in term:
                parts.append(term["definition"])
            parts.extend(term.get("synonyms", [])[:3])   # top 3 synonyms only
            term["embed_text"] = " | ".join(filter(None, parts))
            term["ontology"]   = name

            all_terms.append(term)
            count += 1

        print(f"  [{name}] {count:,} valid terms loaded")

    print(f"\n  Total: {len(all_terms):,} terms across CL + UBERON + EFO")
    return all_terms
