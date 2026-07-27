"""
tools/meta_analysis.py — Aggregate statistics across multiple GEO datasets.

Pure Python — no LLM calls. Takes a list of dataset metadata dicts (from
search_geo) and computes summary statistics for the meta-analysis dashboard.
"""

import re
from collections import Counter
from typing import Any


# Common English stopwords + generic bio terms to exclude from title word clouds.
_STOPWORDS = frozenset(
    "a an the and or but in on of to for with from by at is are was were "
    "be been being have has had do does did will would shall should may might "
    "can could not no nor this that these those it its we our they their "
    "using via between through during after before into upon within without "
    "also both each all any more most other some such than too very so as "
    "if then else when where while which what who whom how "
    "study analysis data gene expression profiling genome high throughput "
    "sequencing seq rna dna chip array based reveals role new novel "
    "identifies identified reveals revealed associated".split()
)


def analyze_metadata(datasets: list[dict]) -> dict:
    """
    Aggregate statistics across multiple GEO dataset metadata records.

    Args:
        datasets: List of dicts from search_geo()["datasets"], each containing
                  gse_id, title, summary, organism, sample_count, platform,
                  submission_date, experiment_type.

    Returns dict with:
        total_datasets      int
        total_samples       int
        organism_counts     dict {organism: count}, sorted descending
        experiment_type_counts  dict {type: count}, sorted descending
        platform_counts     dict {platform: count}, sorted descending
        yearly_counts       dict {year: count}, sorted ascending
        sample_count_stats  dict {min, max, mean, median}
        top_title_terms     list of (term, count) tuples, top 20
        datasets            the original list (passed through for convenience)
    """
    # Filter out error entries
    valid = [d for d in datasets if "error" not in d]

    if not valid:
        return _empty_result(datasets)

    # ── Organism distribution ──────────────────────────────────────────────────
    organisms = [d.get("organism", "Unknown") or "Unknown" for d in valid]
    organism_counts = _sorted_counter(organisms)

    # ── Experiment type breakdown ──────────────────────────────────────────────
    exp_types = [d.get("experiment_type", "Unknown") or "Unknown" for d in valid]
    experiment_type_counts = _sorted_counter(exp_types)

    # ── Platform usage ─────────────────────────────────────────────────────────
    platforms = [d.get("platform", "Unknown") or "Unknown" for d in valid]
    platform_counts = _sorted_counter(platforms)

    # ── Submission timeline ────────────────────────────────────────────────────
    years = []
    for d in valid:
        date_str = d.get("submission_date", "")
        year = _extract_year(date_str)
        if year:
            years.append(year)
    yearly_counts = dict(sorted(Counter(years).items()))

    # ── Sample count statistics ────────────────────────────────────────────────
    sample_counts = [d.get("sample_count", 0) or 0 for d in valid]
    sample_count_stats = _compute_stats(sample_counts)

    total_samples = sum(sample_counts)

    # ── Top terms from titles ──────────────────────────────────────────────────
    title_terms = _extract_title_terms(valid)

    return {
        "total_datasets":         len(valid),
        "total_samples":          total_samples,
        "organism_counts":        organism_counts,
        "experiment_type_counts": experiment_type_counts,
        "platform_counts":        platform_counts,
        "yearly_counts":          yearly_counts,
        "sample_count_stats":     sample_count_stats,
        "top_title_terms":        title_terms,
        "datasets":               datasets,
    }


def build_llm_summary_prompt(query: str, analysis: dict) -> str:
    """
    Build a prompt for the LLM to generate a natural-language narrative
    summary of the meta-analysis findings.

    Returns a prompt string ready to send to the LLM.
    """
    org_lines = "\n".join(
        f"  - {org}: {count}" for org, count in analysis["organism_counts"].items()
    )
    exp_lines = "\n".join(
        f"  - {t}: {count}" for t, count in analysis["experiment_type_counts"].items()
    )
    year_lines = "\n".join(
        f"  - {y}: {count}" for y, count in analysis["yearly_counts"].items()
    )
    top_terms = ", ".join(
        f"{term} ({count})" for term, count in analysis["top_title_terms"][:15]
    )
    stats = analysis["sample_count_stats"]

    return f"""You are a bioinformatics research analyst. Based on a GEO database meta-analysis, write a clear, insightful narrative summary of the findings.

SEARCH QUERY: "{query}"
RESULTS: {analysis['total_datasets']} datasets found, {analysis['total_samples']} total samples

ORGANISM DISTRIBUTION:
{org_lines}

EXPERIMENT TYPES:
{exp_lines}

SUBMISSION TIMELINE (by year):
{year_lines}

SAMPLE COUNT STATISTICS:
  - Min: {stats['min']}, Max: {stats['max']}, Mean: {stats['mean']:.1f}, Median: {stats['median']:.1f}

TOP TERMS IN STUDY TITLES:
  {top_terms}

Write a 3-5 paragraph narrative summary covering:
1. Overview: what this search reveals about the research landscape
2. Organism and experimental focus: dominant model systems and why
3. Methodological trends: experiment types and platforms used
4. Temporal trends: how interest has evolved over time
5. Key observations: anything notable or surprising in the data

Be specific with numbers. Write in a scientific but accessible tone. Do NOT use bullet points — write flowing prose paragraphs."""


# ── Internal helpers ───────────────────────────────────────────────────────────

def _empty_result(datasets: list[dict]) -> dict:
    return {
        "total_datasets":         0,
        "total_samples":          0,
        "organism_counts":        {},
        "experiment_type_counts": {},
        "platform_counts":        {},
        "yearly_counts":          {},
        "sample_count_stats":     {"min": 0, "max": 0, "mean": 0.0, "median": 0.0},
        "top_title_terms":        [],
        "datasets":               datasets,
    }


def _sorted_counter(items: list[str]) -> dict:
    """Count items and return as dict sorted by frequency (descending)."""
    counter = Counter(items)
    return dict(counter.most_common())


def _extract_year(date_str: str) -> str | None:
    """Extract a 4-digit year from a date string like '2025/04/24' or '2025'."""
    if not date_str:
        return None
    match = re.search(r"(19|20)\d{2}", str(date_str))
    return match.group(0) if match else None


def _compute_stats(values: list[int | float]) -> dict:
    """Compute min, max, mean, median for a list of numbers."""
    if not values:
        return {"min": 0, "max": 0, "mean": 0.0, "median": 0.0}

    sorted_v = sorted(values)
    n = len(sorted_v)
    median = (
        sorted_v[n // 2]
        if n % 2 == 1
        else (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2
    )
    return {
        "min":    min(values),
        "max":    max(values),
        "mean":   sum(values) / len(values),
        "median": float(median),
    }


def _extract_title_terms(datasets: list[dict], top_n: int = 20) -> list[tuple]:
    """
    Extract the most frequent meaningful terms from study titles.
    Returns list of (term, count) tuples.
    """
    counter: Counter = Counter()
    for d in datasets:
        title = d.get("title", "")
        # Tokenize: lowercase, remove non-alpha, filter short/stopwords
        words = re.findall(r"[a-z]{3,}", title.lower())
        meaningful = [w for w in words if w not in _STOPWORDS]
        counter.update(meaningful)

    return counter.most_common(top_n)
