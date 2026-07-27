"""
tools/ontology_tool.py — Agent-facing ontology lookup.

Thin wrapper around OntologyVectorStore that adds:
    - Lazy singleton loading (index is only read from disk once)
    - low_confidence flag that drives the agent's PubMed fallback logic
    - clean return schema for the ReAct / LangChain / LangGraph agents
    - cost-gated LLM term disambiguation (see PASS 2 below)

The low_confidence flag is the "Agentic RAG" trigger:
    If score < threshold → agent MUST call search_pubmed before retrying.

TWO-PASS LOOKUP:
    Pass 1 (always runs, no LLM):
        Raw embedding search on raw_term as-is. Fast (<50ms), zero cost.
        This resolves the vast majority of clean GEO terms correctly.

    Pass 2 (only runs if Pass 1 scored below threshold, and only if
            settings.ENABLE_TERM_NORMALIZATION is True):
        Ask an LLM to disambiguate the raw term — e.g. "macs" could be the
        MACS isolation METHOD or slang for "macrophages" CELL TYPE; the
        embedding alone can't tell, but an LLM given the field name usually
        can. Re-run the embedding search on the disambiguated term. Keep
        whichever pass scored higher — normalization can only help, never
        actively make a correct Pass-1 result worse.

    This means: clean terms never pay an LLM round-trip. Only genuinely
    ambiguous terms do. See rag/term_normalizer.py for the disambiguation
    logic and its fail-safe contract.
"""

from typing import Optional
from rag.vector_store import OntologyVectorStore
from config import settings

# ── Singleton store ────────────────────────────────────────────────────────────
_store: Optional[OntologyVectorStore] = None


def _get_store() -> OntologyVectorStore:
    global _store
    if _store is None:
        _store = OntologyVectorStore()
        if not _store.load():
            raise RuntimeError(
                "Ontology index not found. Build it first:\n"
                "    python scripts/build_index.py\n"
                "First run takes ~10–15 min on an 8 GB VRAM GPU."
            )
    return _store


def _empty_result(raw_term: str) -> dict:
    return {
        "raw_term":        raw_term,
        "normalized_term": None,
        "term_id":         None,
        "name":            None,
        "definition":      None,
        "ontology":        None,
        "score":           0.0,
        "low_confidence":  True,
        "candidates":      [],
    }


def _to_result(
    raw_term: str,
    results: list[dict],
    threshold: float,
    normalized_term: Optional[str] = None,
) -> dict:
    best = results[0]
    return {
        "raw_term":        raw_term,
        "normalized_term": normalized_term,
        "term_id":         best["id"],
        "name":            best["name"],
        "definition":      best.get("definition", ""),
        "ontology":        best["ontology"],
        "score":           round(best["score"], 4),
        "low_confidence":  best["score"] < threshold,
        "candidates": [
            {"id": r["id"], "name": r["name"], "score": round(r["score"], 4)}
            for r in results[1:4]
        ],
    }


# ── Public tool function ───────────────────────────────────────────────────────

def map_to_ontology(
    raw_term: str,
    threshold: float | None = None,
    field_context: str = "",
    context_hint: str = "",
) -> dict:
    """
    Map a raw biological term to its best ontology match.

    Args:
        raw_term:      e.g. "lung macs", "NK cell", "MACS-isolated macs"
        threshold:     Confidence cutoff. Below this → low_confidence=True.
                        Defaults to settings.ONTOLOGY_CONFIDENCE_THRESHOLD (0.70).
        field_context: Optional GEO characteristic field name, e.g. "cell type".
                        Passed to the Pass-2 LLM disambiguator if triggered.
        context_hint:  Optional external evidence (e.g. a PubMed abstract
                        snippet) for the Pass-2 disambiguator. Pass this when
                        retrying after a PubMed fallback search.

    Returns dict:
        raw_term         original input string, always preserved verbatim
        normalized_term  what Pass 2 actually searched with, or None if
                          Pass 2 never ran (clean term) or failed (no LLM
                          available / disabled) — surfaced for the "Agent's
                          Thoughts" transparency panel
        term_id          e.g. "CL:0000583"  (None if no match found)
        name             e.g. "alveolar macrophage"
        definition       prose definition from the ontology
        ontology         "CL" | "UBERON" | "EFO"
        score            float 0.0–1.0  (cosine similarity, winning pass)
        low_confidence   bool — True  → agent must call search_pubmed first
        candidates       next 3 ranked alternatives for human review
    """
    if threshold is None:
        threshold = settings.ONTOLOGY_CONFIDENCE_THRESHOLD

    store = _get_store()
    raw_term = raw_term.strip()

    # ── Pass 1: cheap embedding search, always runs ───────────────────────────
    results = store.search(raw_term, top_k=5)
    if not results:
        pass1_result = _empty_result(raw_term)
    else:
        pass1_result = _to_result(raw_term, results, threshold)

    if not pass1_result["low_confidence"]:
        return pass1_result  # clean term — done, zero LLM cost

    # ── Pass 2: LLM disambiguation, only on low-confidence Pass 1 ─────────────
    if not settings.ENABLE_TERM_NORMALIZATION:
        return pass1_result

    from rag.term_normalizer import normalize_term
    normalized = normalize_term(
        raw_term, field_context=field_context, context_hint=context_hint
    )
    if not normalized or normalized.lower() == raw_term.lower():
        return pass1_result  # disambiguation unavailable or made no change

    retried = store.search(normalized, top_k=5)
    if not retried:
        return pass1_result

    pass2_result = _to_result(raw_term, retried, threshold, normalized_term=normalized)

    # Keep whichever pass scored higher — normalization must only ever help.
    return pass2_result if pass2_result["score"] > pass1_result["score"] else pass1_result
