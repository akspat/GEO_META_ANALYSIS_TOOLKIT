"""
rag/term_normalizer.py — Optional LLM-based query disambiguation.

WHY THIS EXISTS:
    Raw GEO characteristics collide method-vs-entity constantly. The
    clearest real example: "macs" can mean:
        (a) MACS = Magnetic-Activated Cell Sorting — an isolation METHOD
        (b) informal shorthand for "macrophages" — a CELL TYPE
    Pure embedding similarity can't reliably tell these apart — both
    readings sit close to plausible, different ontology terms. An LLM
    given the source field name ("cell type: macs-isolated macs") usually
    can.

WHERE THIS IS CALLED FROM:
    tools/ontology_tool.py::map_to_ontology() — and ONLY when a first-pass
    raw embedding search already scored below the confidence threshold.
    Clean, unambiguous terms (the majority case) never pay this cost.
    This mirrors the project's own "Agentic RAG" pattern: cheap path first,
    escalate to reasoning only when the cheap path is uncertain.

FAILURE CONTRACT:
    Returns None on ANY failure — Ollama down, JSON parse error, model
    returned an empty/missing field, normalization disabled in settings.
    Callers MUST treat None as "fall back to the raw term, unchanged."
    This function can only ever improve a result; it must never be able
    to break the pipeline by raising.
"""

from typing import Optional
from utils.llm_client import llm
from config import settings

_SYSTEM_PROMPT = (
    "You are a biomedical terminology normalizer. Given a raw, possibly "
    "jargon-laden annotation from a GEO sample characteristic, extract the "
    "single canonical biological entity (a cell type, tissue, or disease "
    "name) that best represents it, suitable for controlled-ontology "
    "lookup. Strip out isolation methods, treatment conditions, or assay "
    "techniques UNLESS the raw term is actually naming a technique itself. "
    "If supporting context is provided, use it to resolve ambiguity. "
    'Respond with ONLY this JSON object, nothing else: '
    '{"normalized_term": "..."}'
)


def normalize_term(
    raw_term: str,
    field_context: str = "",
    context_hint: str = "",
) -> Optional[str]:
    """
    Args:
        raw_term:      e.g. "MACS-isolated macs"
        field_context: GEO characteristic field name, e.g. "cell type".
                       Cheap and always available — pass it whenever you have it.
        context_hint:  Optional external evidence, e.g. a PubMed abstract
                       snippet gathered during an agentic repair loop.
                       Truncated to 300 chars to keep the prompt small.

    Returns:
        A cleaned term string, or None if normalization is disabled,
        unavailable, or failed. Callers fall back to raw_term on None.
    """
    if not settings.ENABLE_TERM_NORMALIZATION:
        return None

    if not raw_term or not raw_term.strip():
        return None

    parts = [f'Raw term: "{raw_term.strip()}"']
    if field_context:
        parts.append(f'Source field: "{field_context.strip()}"')
    if context_hint:
        parts.append(f'Supporting context: "{context_hint.strip()[:300]}"')
    prompt = "\n".join(parts)

    try:
        result = llm.generate_json(prompt, system=_SYSTEM_PROMPT, max_tokens=80)
        cleaned = str(result.get("normalized_term", "")).strip()
        return cleaned or None
    except Exception:
        # Ollama unreachable, malformed JSON, missing key, model returned
        # garbage — an optional enhancement must never break the required
        # pipeline. Silent fallback is the correct behavior here, not a bug.
        return None
