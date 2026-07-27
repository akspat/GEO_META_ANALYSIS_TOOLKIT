"""
tools/pubmed_tool.py — PubMed abstract search via NCBI E-utilities.

Used by the agent ONLY when ontology mapping returns low_confidence=True.
The agent reads the abstract to understand what a term means in context,
then retries map_to_ontology with a more precise query.

This is the agentic RAG pattern:
    low confidence → fetch external context → retry with context.
"""

import time
import requests
import xml.etree.ElementTree as ET
from config import settings

_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_SLEEP  = 0.11 if settings.NCBI_API_KEY else 0.34


def _ncbi_params(extra: dict) -> dict:
    p = {"email": settings.NCBI_EMAIL, **extra}
    if settings.NCBI_API_KEY:
        p["api_key"] = settings.NCBI_API_KEY
    return p


def search_pubmed(query: str, max_results: int = 5) -> list[dict]:
    """
    Search PubMed and return titles + truncated abstracts.

    Args:
        query:       Free-text search, e.g. "NSCLC tumor microenvironment"
        max_results: Number of articles to return (default 5)

    Returns:
        List of dicts: {pmid, title, abstract, year, url}
    """
    # Step 1 — search for PMIDs
    time.sleep(_SLEEP)
    search_resp = requests.get(
        f"{_EUTILS}/esearch.fcgi",
        params=_ncbi_params(
            {
                "db":      "pubmed",
                "term":    query,
                "retmax":  max_results,
                "retmode": "json",
                "sort":    "relevance",
            }
        ),
        timeout=30,
    )
    search_resp.raise_for_status()
    ids = search_resp.json().get("esearchresult", {}).get("idlist", [])

    if not ids:
        return []

    # Step 2 — fetch abstracts as XML
    time.sleep(_SLEEP)
    fetch_resp = requests.get(
        f"{_EUTILS}/efetch.fcgi",
        params=_ncbi_params(
            {
                "db":      "pubmed",
                "id":      ",".join(ids),
                "rettype": "abstract",
                "retmode": "xml",
            }
        ),
        timeout=30,
    )
    fetch_resp.raise_for_status()

    return _parse_xml(fetch_resp.text)


def _parse_xml(xml_text: str) -> list[dict]:
    """Parse PubMed eFetch XML into clean article dicts."""
    articles: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    for article in root.findall(".//PubmedArticle"):
        pmid  = article.findtext(".//PMID", default="")
        title = article.findtext(".//ArticleTitle", default="")
        year  = (
            article.findtext(".//PubDate/Year")
            or article.findtext(".//PubDate/MedlineDate", default="")
        )

        # Structured abstracts have multiple <AbstractText Label="..."> nodes.
        parts: list[str] = []
        for node in article.findall(".//AbstractText"):
            label = node.get("Label", "")
            text  = (node.text or "").strip()
            if label:
                parts.append(f"{label}: {text}")
            elif text:
                parts.append(text)
        abstract = " ".join(parts)[:500]   # cap at 500 chars for LLM context

        articles.append(
            {
                "pmid":     pmid,
                "title":    title,
                "abstract": abstract,
                "year":     year,
                "url":      f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            }
        )

    return articles
