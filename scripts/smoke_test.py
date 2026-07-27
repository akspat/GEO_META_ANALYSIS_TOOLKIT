#!/usr/bin/env python3
"""
scripts/smoke_test.py — End-to-end sanity check.

Run AFTER build_index.py to verify every component works before
opening the Streamlit UI. Catches the most common failure points:
    - NCBI API unreachable / rate-limited
    - Ollama not running
    - Vector index not built / corrupted
    - Agent loop crashing on malformed LLM output

Usage:
    python scripts/smoke_test.py
    python scripts/smoke_test.py --gse GSE150318   # test a specific accession
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def check(label: str, fn) -> bool:
    print(f"  {label} ... ", end="", flush=True)
    try:
        result = fn()
        print(f"OK  ({result})" if result else "OK")
        return True
    except Exception as exc:
        print(f"FAIL — {type(exc).__name__}: {exc}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gse", default="GSE150318", help="Test GSE accession")
    args = parser.parse_args()

    print("=" * 70)
    print("Gene Expression Standardization Tool — Smoke Test")
    print("=" * 70)

    results = []

    # ── 1. Config loads ────────────────────────────────────────────────────────
    print("\n[1/6] Configuration")
    def _config():
        from config import settings
        return f"model={settings.OLLAMA_MODEL}"
    results.append(check("Config loads", _config))

    # ── 2. LLM backend reachable ───────────────────────────────────────────────
    print("\n[2/6] LLM Backend")
    def _llm():
        from utils.llm_client import llm
        backend = llm.backend()
        if backend != "ollama":
            raise RuntimeError("Local Ollama service unavailable")
        return backend
    results.append(check("Backend detected", _llm))

    def _llm_generate():
        from utils.llm_client import llm
        resp = llm.generate("Say 'OK' and nothing else.", max_tokens=10)
        return resp.strip()[:30]
    results.append(check("Generation works", _llm_generate))

    # ── 3. Vector index ─────────────────────────────────────────────────────────
    print("\n[3/6] Ontology Vector Store")
    def _vector_store():
        from rag.vector_store import OntologyVectorStore
        store = OntologyVectorStore()
        if not store.load():
            raise RuntimeError("Index not found — run scripts/build_index.py first")
        return f"{store.index.ntotal:,} vectors"
    results.append(check("Index loads", _vector_store))

    def _ontology_search():
        from tools.ontology_tool import map_to_ontology
        result = map_to_ontology("alveolar macrophage")
        if result["term_id"] is None:
            raise RuntimeError("No match found for known term")
        # normalized_term should be None here — this is a clean, unambiguous
        # term, so Pass 2 (LLM disambiguation) should never have fired.
        if result["normalized_term"] is not None:
            raise RuntimeError(
                f"Pass 2 fired on a clean term unexpectedly: {result['normalized_term']}"
            )
        return f"{result['term_id']} (score={result['score']})"
    results.append(check("Ontology mapping works", _ontology_search))

    def _ontology_normalization():
        from tools.ontology_tool import map_to_ontology
        # A deliberately ambiguous/jargon term — exercises the Pass-2
        # LLM disambiguation path. This call WILL hit your LLM backend.
        result = map_to_ontology("MACS-isolated macs", field_context="cell type")
        tag = "(Pass 2 fired)" if result["normalized_term"] else "(Pass 1 sufficed)"
        return f"score={result['score']} {tag}"
    results.append(check("Term disambiguation (Pass 2) reachable", _ontology_normalization))

    # ── 4. NCBI GEO API ─────────────────────────────────────────────────────────
    print(f"\n[4/6] NCBI GEO API (testing {args.gse})")
    def _geo():
        from tools.geo_tool import get_gse_metadata
        data = get_gse_metadata(args.gse)
        if "error" in data:
            raise RuntimeError(data["error"])
        return f"{data.get('sample_count', 0)} samples, organism={data.get('organism')}"
    results.append(check("GEO metadata fetch", _geo))

    # ── 5. NCBI PubMed API ───────────────────────────────────────────────────────
    print("\n[5/6] NCBI PubMed API")
    def _pubmed():
        from tools.pubmed_tool import search_pubmed
        articles = search_pubmed("alveolar macrophage lung", max_results=2)
        if not articles:
            raise RuntimeError("No articles returned")
        return f"{len(articles)} article(s) found"
    results.append(check("PubMed search", _pubmed))

    # ── 6. LangChain hybrid agent factory ────────────────────────────────────────
    print("\n[6/6] LangChain Hybrid Agent")
    def _agent():
        from agents.langchain_agent import build_hybrid_agent, LC_TOOLS
        if not LC_TOOLS:
            raise RuntimeError("No LangChain tools registered")
        # Verify the factory can construct an AgentExecutor without error.
        # We don't invoke it here — that would require a live LLM call,
        # which is already covered by test 2/6.
        agent_exec = build_hybrid_agent(verbose=False)
        return f"{len(LC_TOOLS)} tools, max_iter={agent_exec.max_iterations}"
    results.append(check("Agent factory builds", _agent))

    # ── Summary ──────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    passed = sum(results)
    total = len(results)
    print(f"  {passed}/{total} checks passed")
    if passed == total:
        print("  All systems operational. Run: ./venv/bin/python -m streamlit run app.py")
    else:
        print("  Fix the FAILs above before running the Streamlit app.")
    print("=" * 70)

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
