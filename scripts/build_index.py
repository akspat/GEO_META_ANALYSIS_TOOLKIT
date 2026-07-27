#!/usr/bin/env python3
"""
scripts/build_index.py — One-time ontology index builder.

Run this ONCE before using the app:
    cd bio_scholar_ai
    python scripts/build_index.py

What it does:
    1. Downloads CL, UBERON, EFO .obo files (~30 MB total) if not cached.
    2. Parses ~50,000 terms.
    3. Embeds all terms using all-MiniLM-L6-v2 on your GPU.
    4. Saves a FAISS index to ./data/vector_store/

Timing on 8 GB VRAM GPU:
    Download:  1–3 min   (depends on connection)
    Parsing:   ~10 sec
    Embedding: 10–15 min (one-time cost — cached forever after)
    TOTAL:     ~15–20 min first run, instant on every run after.

If you see "CUDA out of memory":
    Lower EMBED_BATCH_SIZE in .env (try 256, then 128).

If this hangs on download:
    GitHub releases can be slow from some networks. Re-run the script —
    partial downloads are NOT resumed, so check file sizes if it seems stuck
    (CL ~15MB, UBERON ~120MB, EFO ~80MB after basic filtering).
"""

import sys
import time
from pathlib import Path

# Allow running as: python scripts/build_index.py  (from project root)
sys.path.insert(0, str(Path(__file__).parent.parent))

from rag.ontology_loader import load_all_ontologies
from rag.vector_store import OntologyVectorStore
from config import settings


def main() -> None:
    print("=" * 70)
    print("Gene Expression Standardization Tool — Ontology Index Builder")
    print("=" * 70)

    store = OntologyVectorStore()
    if store.load():
        print(f"\n  Index already exists at {settings.VECTOR_STORE_PATH}/")
        resp = input("  Rebuild from scratch? [y/N]: ").strip().lower()
        if resp != "y":
            print("  Skipping. Existing index will be used.")
            return

    t0 = time.time()

    print("\n[1/2] Downloading & parsing ontologies (CL, UBERON, EFO)...")
    print("      First run: ~30MB total download, ~10-20 sec parse.\n")
    terms = load_all_ontologies()

    if not terms:
        print("\n  ERROR: No terms loaded. Check your internet connection")
        print("  and that GitHub is reachable, then retry.")
        sys.exit(1)

    print(f"\n[2/2] Building FAISS index (batch_size={settings.EMBED_BATCH_SIZE})...")
    print("      8 GB VRAM GPU: expect 10-15 min for ~50k terms.\n")

    fresh_store = OntologyVectorStore()
    fresh_store.build(terms)

    elapsed = time.time() - t0
    print(f"\n{'=' * 70}")
    print(f"  DONE in {elapsed / 60:.1f} minutes.")
    print(f"  Index saved to: {settings.VECTOR_STORE_PATH}/")
    print("  You can now run: streamlit run app.py")
    print("=" * 70)


if __name__ == "__main__":
    main()
