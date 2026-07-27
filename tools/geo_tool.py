"""
tools/geo_tool.py — NCBI GEO metadata via E-utilities API.

Two main entry points:
    search_geo(query)           → search GEO with free-text, return dataset summaries
    get_gse_metadata(gse_id)    → fetch full metadata for a single GSE accession

Rate limits enforced here:
    No NCBI key  →  3  requests / second  (0.34 s sleep)
    Free NCBI key →  10 requests / second  (0.11 s sleep)
    Register: https://www.ncbi.nlm.nih.gov/account/

E-utilities docs: https://www.ncbi.nlm.nih.gov/books/NBK25501/
"""

import re
import time
import requests
import xml.etree.ElementTree as ET
from typing import Optional
from config import settings

_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
# Seconds to sleep between requests (respects NCBI rate limits).
_SLEEP = 0.11 if settings.NCBI_API_KEY else 0.34


# ── Query expansion ───────────────────────────────────────────────────────────
# Maps common user shorthand → OR-joined alternatives for broader NCBI matches.
# Patterns are case-insensitive, applied longest-first to avoid partial matches.
# Uses placeholder markers to prevent already-expanded text from being re-expanded.

_EXPANSIONS = [
    # Compound patterns (longest first — must match before individual terms)
    (r"\bsingle\s*cell\s*rna\s*-?\s*seq\b", "«scRNA»"),
    (r"\bsc\s*rna\s*-?\s*seq\b",            "«scRNA»"),

    # Individual -seq patterns
    (r"\brna\s*-?\s*seq\b",                 "«RNA»"),
    (r"\batac\s*-?\s*seq\b",                "«ATAC»"),
    (r"\bchip\s*-?\s*seq\b",                "«ChIP»"),

    # Single-cell (after compound patterns already consumed)
    (r"\bsingle\s*cell\b",                  "«SC»"),

    # Other common shorthand
    (r"\bspatial\s*transcriptom\w*\b",      "«SPATIAL»"),
    (r"\bbulk\s*rna\b",                     "«BULK»"),
    (r"\bwgs\b",                            "«WGS»"),
    (r"\bwes\b",                            "«WES»"),
]

# Second pass: replace markers with their OR-joined expansions.
_MARKER_MAP = {
    "«scRNA»":   "(single cell RNA-seq OR scRNA-seq OR scRNAseq)",
    "«RNA»":     "(RNA-seq OR RNAseq OR RNA sequencing)",
    "«ATAC»":    "(ATAC-seq OR ATACseq)",
    "«ChIP»":    "(ChIP-seq OR ChIPseq OR ChIP sequencing)",
    "«SC»":      "(single cell OR single-cell)",
    "«SPATIAL»": "(spatial transcriptomics OR Visium OR MERFISH OR seqFISH)",
    "«BULK»":    "(bulk RNA OR bulk RNA-seq OR bulk RNAseq)",
    "«WGS»":     "(WGS OR whole genome sequencing)",
    "«WES»":     "(WES OR whole exome sequencing)",
}


def _expand_query(query: str) -> str:
    """
    Expand common shorthand terms into OR-joined alternatives.

    E.g. "rainbow trout single cell rnaseq"
       → "rainbow trout (single cell RNA-seq OR scRNA-seq OR scRNAseq)"

    Two-pass approach: first replace matches with unique markers,
    then substitute the markers with the actual OR expansions.
    This prevents nested re-expansion.
    """
    expanded = query
    # Pass 1: regex → markers
    for pattern, marker in _EXPANSIONS:
        expanded = re.sub(pattern, marker, expanded, flags=re.IGNORECASE)
    # Pass 2: markers → OR expansions
    for marker, replacement in _MARKER_MAP.items():
        expanded = expanded.replace(marker, replacement)
    return expanded


def _get(endpoint: str, params: dict) -> requests.Response:
    """Rate-limited GET to NCBI E-utilities."""
    time.sleep(_SLEEP)
    params["email"] = settings.NCBI_EMAIL
    if settings.NCBI_API_KEY:
        params["api_key"] = settings.NCBI_API_KEY
    resp = requests.get(f"{_EUTILS}/{endpoint}", params=params, timeout=30)
    resp.raise_for_status()
    return resp



# ── Query fallback helpers ─────────────────────────────────────────────────────

def _clean_fallback_keywords(query: str) -> list[str]:
    """Strip strict Entrez syntax, boolean ops, brackets, and field tags to extract keywords."""
    clean = re.sub(r"\[\w+\]", "", query)
    clean = clean.replace('"', '').replace("'", "")
    clean = re.sub(r"\b(AND|OR|NOT)\b", " ", clean, flags=re.IGNORECASE)
    clean = re.sub(r"[\(\)\*\+]", " ", clean)
    keywords = [w.strip() for w in clean.split() if len(w.strip()) > 2]
    return keywords


def _execute_esearch(term: str, max_results: int) -> tuple[list[str], int]:
    search = _get(
        "esearch.fcgi",
        {
            "db":      "gds",
            "term":    term,
            "retmax":  max_results,
            "retmode": "json",
            "sort":    "relevance",
        },
    )
    res = search.json().get("esearchresult", {})
    return res.get("idlist", []), int(res.get("count", 0))


# ── Search function ────────────────────────────────────────────────────────────

def search_geo(
    query: str,
    max_results: int | None = None,
    progress_callback=None,
) -> dict:
    """
    Search NCBI GEO with a free-text query and return dataset summaries.
    Includes an automatic fallback to natural language keyword matching if strict syntax fails.
    """
    if max_results is None:
        max_results = settings.GEO_SEARCH_MAX_RESULTS

    query = query.strip()
    if not query:
        return {"query": query, "total_found": 0, "datasets": [], "error": "Empty query"}

    expanded = _expand_query(query)
    search_term = f"({expanded}) AND gse[ETYP]"
    ids, total_found = _execute_esearch(search_term, max_results)
    fallback_triggered = False

    # ── Fallback Mechanism ────────────────────────────────────────────────────
    if not ids:
        keywords = _clean_fallback_keywords(query)
        if keywords:
            # Attempt 1: All keywords joined by space (implicit Entrez relevance)
            fb_term_1 = f"({' '.join(keywords)}) AND gse[ETYP]"
            ids, total_found = _execute_esearch(fb_term_1, max_results)
            fallback_triggered = True

            # Attempt 2: If still 0, join by OR to guarantee finding related datasets
            if not ids and len(keywords) > 1:
                fb_term_2 = f"({' OR '.join(keywords)}) AND gse[ETYP]"
                ids, total_found = _execute_esearch(fb_term_2, max_results)

    if not ids:
        return {
            "query":       query,
            "total_found": 0,
            "datasets":    [],
            "fallback":    fallback_triggered,
        }

    # Step 2: Batch fetch summaries for all IDs
    datasets = []
    for i, gds_id in enumerate(ids):
        try:
            summary = _get(
                "esummary.fcgi",
                {"db": "gds", "id": gds_id, "retmode": "json"},
            )
            doc = summary.json().get("result", {}).get(gds_id, {})

            # Only include GSE series entries (skip GDS, GPL, GSM)
            accession = doc.get("accession", "")
            if not accession.upper().startswith("GSE"):
                # Try to extract from the entrytype field
                gse_acc = doc.get("gse", "")
                if gse_acc:
                    accession = f"GSE{gse_acc}"
                else:
                    accession = f"GSE-{gds_id}"

            datasets.append({
                "gse_id":          accession,
                "title":           doc.get("title", ""),
                "summary":         (doc.get("summary") or "")[:600],
                "organism":        doc.get("taxon", ""),
                "sample_count":    doc.get("n_samples", 0),
                "platform":        doc.get("gpl", ""),
                "submission_date": doc.get("pdat", ""),
                "experiment_type": doc.get("gdstype", ""),
            })
        except Exception as exc:
            datasets.append({
                "gse_id": f"ERROR-{gds_id}",
                "error":  str(exc),
            })

        if progress_callback:
            progress_callback(i + 1, len(ids))

    return {
        "query":       query,
        "total_found": total_found,
        "datasets":    datasets,
        "fallback":    fallback_triggered,
    }


# ── Single dataset detail ──────────────────────────────────────────────────────

def get_gse_metadata(gse_id: str) -> dict:
    """
    Fetch detailed metadata for a single GEO Series (GSE) accession,
    including sample-level characteristics.

    Args:
        gse_id: e.g. "GSE150318"  (case-insensitive)

    Returns dict with keys:
        gse_id, title, summary, organism, sample_count,
        platform, submission_date, experiment_type,
        samples  (list of {gsm_id, title, characteristics})
    """
    gse_id = gse_id.strip().upper()

    # Step 1: accession → GDS numeric ID
    search = _get(
        "esearch.fcgi",
        {
            "db":      "gds",
            "term":    f"{gse_id}[ACCN]",
            "retmax":  1,
            "retmode": "json",
        },
    )
    ids = search.json().get("esearchresult", {}).get("idlist", [])
    if not ids:
        return {
            "error":  f"No GEO record found for '{gse_id}'. Check the accession.",
            "gse_id": gse_id,
        }

    # Step 2: series-level summary
    summary = _get(
        "esummary.fcgi",
        {"db": "gds", "id": ids[0], "retmode": "json"},
    )
    doc = summary.json().get("result", {}).get(ids[0], {})

    return {
        "gse_id":          gse_id,
        "title":           doc.get("title", ""),
        "summary":         (doc.get("summary") or "")[:600],
        "organism":        doc.get("taxon", ""),
        "sample_count":    doc.get("n_samples", 0),
        "platform":        doc.get("gpl", ""),
        "submission_date": doc.get("pdat", ""),
        "experiment_type": doc.get("gdstype", ""),
        "samples":         _fetch_samples(gse_id, max_samples=8),
    }


# ── Internal helpers ───────────────────────────────────────────────────────────

def _fetch_samples(gse_id: str, max_samples: int = 8) -> list[dict]:
    """
    Fetch GSM (sample) records linked to a GSE.
    Each GSM contains raw 'characteristics' — the messy terms
    that the ontology mapper resolves to controlled IDs.
    """
    search = _get(
        "esearch.fcgi",
        {
            "db":      "gds",
            "term":    f"{gse_id}[ACCN] AND gsm[ETYP]",
            "retmax":  max_samples,
            "retmode": "json",
        },
    )
    sample_ids = search.json().get("esearchresult", {}).get("idlist", [])
    if not sample_ids:
        return []

    samples: list[dict] = []
    for sid in sample_ids:
        try:
            s = _get(
                "esummary.fcgi",
                {"db": "gds", "id": sid, "retmode": "json"},
            )
            sdata = s.json().get("result", {}).get(sid, {})

            # Parse raw characteristic strings → {field, value} dicts.
            raw_chars = sdata.get("characteristics", [])
            parsed: list[dict] = []
            for c in raw_chars:
                text = str(c)
                if ":" in text:
                    field, _, value = text.partition(":")
                    parsed.append(
                        {"field": field.strip(), "value": value.strip()}
                    )
                else:
                    parsed.append({"field": "characteristic", "value": text.strip()})

            samples.append(
                {
                    "gsm_id":          sdata.get("accession", sid),
                    "title":           sdata.get("title", ""),
                    "characteristics": parsed,
                }
            )
        except Exception as exc:
            samples.append({"gsm_id": sid, "error": str(exc)})

    return samples
