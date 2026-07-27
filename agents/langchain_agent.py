"""
agents/langchain_agent.py — LangChain ReAct Agent for GEO Meta-Analysis.

Same tools as react_agent.py, but wrapped in LangChain's @tool decorator
and driven by AgentExecutor.
"""

import json
from langchain.tools import tool
from langchain.agents import AgentExecutor, create_react_agent
from langchain.prompts import PromptTemplate
from config import settings


# ── Tool definitions ──────────────────────────────────────────────────────────

_cached_datasets = []

@tool
def geo_search_tool(query: str) -> str:
    """
    Search NCBI GEO with a free-text query.
    Input is a search query like 'lung cancer single cell RNA-seq'.
    Returns total_found count and a list of dataset metadata.
    Call this FIRST for any search query.
    """
    global _cached_datasets
    from tools.geo_tool import search_geo
    result = search_geo(query.strip())
    _cached_datasets = result.get("datasets", [])
    # Return concise summary without huge dataset text array to save context
    summary = {
        "query": result.get("query"),
        "total_found": result.get("total_found"),
        "fetched_count": len(_cached_datasets),
        "fallback_triggered": result.get("fallback", False)
    }
    return json.dumps(summary)


@tool
def metadata_analysis_tool(dummy_input: str) -> str:
    """
    Compute aggregate statistics across GEO datasets.
    Input is literally anything (e.g. 'analyze'). Uses cached search results.
    Returns organism_counts, experiment_type_counts, platform_counts,
    yearly_counts, sample_count_stats, top_title_terms.
    Call this AFTER geo_search_tool to analyze the results.
    """
    global _cached_datasets
    from tools.meta_analysis import analyze_metadata
    if not _cached_datasets:
        return json.dumps({"error": "No datasets available to analyze. Call geo_search_tool first."})
    result = analyze_metadata(_cached_datasets)
    result_copy = {k: v for k, v in result.items() if k != "datasets"}
    return json.dumps(result_copy, default=str)


@tool
def pubmed_search_tool(query: str) -> str:
    """
    Search PubMed for biological context.
    Input is a free-text search query.
    Use this to gather additional context about the research area
    for the narrative summary.
    """
    from tools.pubmed_tool import search_pubmed
    return json.dumps(search_pubmed(query.strip(), max_results=3))


LC_TOOLS = [geo_search_tool, metadata_analysis_tool, pubmed_search_tool]


# ── Prompt template ────────────────────────────────────────────────────────────

REACT_PROMPT = PromptTemplate.from_template(
    """\
You are the GEO Meta-Analysis Toolkit, a bioinformatics research analyst agent.
Search GEO for datasets matching a query, analyze the metadata, and write a
comprehensive narrative summary of the research landscape.

Rules:
1. Call geo_search_tool FIRST with the search query.
2. Call metadata_analysis_tool with input "analyze" to process the search results.
3. Write a detailed narrative summary as your Final Answer.
4. Final Answer must be flowing prose paragraphs with specific numbers.

Available tools:
{tools}

Tool names: {tool_names}

Conversation history:
{agent_scratchpad}

Task: {input}
Thought:"""
)


# ── Agent factory ──────────────────────────────────────────────────────────────

def build_langchain_agent(verbose: bool = True) -> AgentExecutor:
    """
    Build and return a LangChain AgentExecutor powered strictly by local Ollama GPU/CPU.
    """
    import requests as req

    try:
        req.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=2).raise_for_status()
    except Exception as e:
        raise RuntimeError(
            f"Local Ollama LLM service is unavailable at {settings.OLLAMA_BASE_URL}.\n"
            f"Please start Ollama and pull the model:\n"
            f"  ollama serve\n"
            f"  ollama pull {settings.OLLAMA_MODEL}"
        ) from e

    from langchain_community.llms import Ollama

    lc_llm = Ollama(
        model=settings.OLLAMA_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=0.1,
    )
    print(f"[LangChain] Backend: Local Ollama ({settings.OLLAMA_MODEL})")

    # ── Assemble and compile ───────────────────────────────────────────────────
    agent = create_react_agent(lc_llm, LC_TOOLS, REACT_PROMPT)

    return AgentExecutor(
        agent=agent,
        tools=LC_TOOLS,
        verbose=verbose,
        max_iterations=settings.AGENT_MAX_STEPS,
        handle_parsing_errors=True,
        return_intermediate_steps=True,
    )


def get_last_analysis() -> dict:
    """Helper for UI to fetch computed aggregates for charts."""
    global _cached_datasets
    if not _cached_datasets:
        return {}
    from tools.meta_analysis import analyze_metadata
    return analyze_metadata(_cached_datasets)


def build_hybrid_agent(verbose: bool = False) -> AgentExecutor:
    """
    Build a specialized LangChain AgentExecutor for Phase 2 literature enrichment using local Ollama.
    """
    import requests as req

    try:
        req.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=2).raise_for_status()
    except Exception as e:
        raise RuntimeError(
            f"Local Ollama LLM service is unavailable at {settings.OLLAMA_BASE_URL}.\n"
            f"Please start Ollama and pull the model:\n"
            f"  ollama serve\n"
            f"  ollama pull {settings.OLLAMA_MODEL}"
        ) from e

    from langchain_community.llms import Ollama
    lc_llm = Ollama(model=settings.OLLAMA_MODEL, base_url=settings.OLLAMA_BASE_URL, temperature=0.1)

    hybrid_tools = [pubmed_search_tool]
    agent = create_react_agent(lc_llm, hybrid_tools, REACT_PROMPT)
    return AgentExecutor(
        agent=agent,
        tools=hybrid_tools,
        verbose=verbose,
        max_iterations=8,
        handle_parsing_errors=True,
        return_intermediate_steps=True,
    )

