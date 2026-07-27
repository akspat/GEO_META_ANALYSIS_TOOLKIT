# 🧬 GEO Meta-Analysis Toolkit

A multi-tool agent that searches NCBI GEO, aggregates metadata across matching datasets,
and generates AI-powered narrative summaries of the research landscape.


## What It Does

Enter a search query (e.g. `"lung cancer single cell RNA-seq"`) and the toolkit will:

1. **Search** NCBI GEO for matching datasets (up to 10000)
2. **Fetch** metadata for each dataset (organism, samples, platform, experiment type, submission date)
3. **Aggregate** statistics across all results (organism distribution, experiment types, submission timeline, top title terms, sample count statistics)
4. **Generate** an LLM-powered narrative summary of the research landscape

## Search Query Syntax

Searches use [NCBI Entrez](https://www.ncbi.nlm.nih.gov/books/NBK25500/) syntax. All words are implicitly joined with AND.

| Syntax | Example | What it does |
|--------|---------|-------------|
| Plain text | `rainbow trout single cell` | Matches all words (implicit AND) |
| `AND` / `OR` / `NOT` | `lung OR liver AND cancer` | Boolean operators |
| `"quotes"` | `"rainbow trout"` | Exact phrase match |
| `*` wildcard | `hepato*` | Truncation — matches hepatocyte, hepatocellular, etc. |
| `[Field]` tags | `Oncorhynchus mykiss[Organism]` | Restrict term to a specific field |
| Combined | `"Oncorhynchus mykiss"[Organism] AND scRNA*` | Field tag + wildcard |

### Examples

```
lung cancer single cell RNA-seq
"rainbow trout" AND single cell
Oncorhynchus mykiss[Organism] AND scRNA*
breast cancer NOT review AND 10x genomics
CRISPR AND "immune cells" AND mouse
```

> **Tip:** Use the Latin species name (e.g. `Oncorhynchus mykiss` instead of `rainbow trout`) for broader results — GEO stores taxonomic names, so scientific names match more datasets.
>
> **Note:** The `+` sign does **not** work as a boolean operator. Use `AND` instead.

## Architecture

```
Streamlit UI (Sleek Dark Dashboard)
        │
        ▼
Unified Hybrid Pipeline (Phase 1 Direct → Phase 2 LangChain → Phase 3 Fallback)
        │
        ▼
  LLM (Ollama medgemma:4b, Local GPU)
        │
   ┌────┴────┬──────────────┐
   ▼         ▼              ▼
NCBI GEO   PubMed      Meta-Analysis
(E-utils)  (E-utils)   (Aggregation Engine)
```

### Unified Architecture

| Engine | Description |
|------|-------------|
| **Unified Hybrid Pipeline** | Combines deterministic linear execution with autonomous AI reasoning. Phase 1 immediately queries NCBI GEO and aggregates distributions for instant chart rendering (~2s). Phase 2 prompts a specialized LangChain ReAct agent to investigate PubMed literature. Phase 3 catches any LLM timeouts and seamlessly auto-degrades to the linear summarizer. Guaranteed 100% success rate on every search! |

### Meta-Analysis Dashboard

The output is presented across four tabs:

| Tab | Content |
|-----|---------|
| **📝 Summary** | Key metrics (datasets, samples, top organism) + LLM-generated narrative |
| **📈 Charts** | Organism distribution, experiment types, submission timeline, top title terms |
| **📋 Datasets** | Full results table (GSE ID, title, organism, samples, type, platform, date) |
| **🔧 Raw Data** | Raw JSON from NCBI API calls |

## Setup (Ubuntu 24)

```bash
# 1. One-time environment check + venv + dependencies
chmod +x scripts/setup_ubuntu.sh
./scripts/setup_ubuntu.sh

# 2. Configure environment variables
cp .env.example .env
nano .env   # at minimum, set NCBI_EMAIL to your real email (NCBI ToS requirement)

# 3. Pull the local LLM (~3.5 GB download, one-time)
ollama pull medgemma:4b

# 4. Build the ontology index (~15–20 min first run, instant after)
python scripts/build_index.py

# 5. Launch the dashboard
./venv/bin/python -m streamlit run app.py
# (or activate venv first: source venv/bin/activate && streamlit run app.py)
```

## Project Structure

```
geo_meta_analysis_toolkit/
│
├── app.py                      Streamlit dashboard — search input, tabbed output
│                                (summary + charts + datasets table + raw data),
│                                and an "Agent's Thoughts" reasoning trace panel.
│
├── config.py                   Centralised settings via pydantic-settings.
│                                Controls LLM backend, NCBI API keys, search
│                                limits, and storage paths.
│
├── requirements.txt            Python dependencies.
├── .env.example                Template — copy to .env and fill in your values.
├── .gitignore                  Excludes caches, venv, secrets, and data/.
│
├── agents/                     Agent implementation:
│   └── langchain_agent.py      LangChain AgentExecutor wrapper — geo_search,
│                                metadata_analysis, pubmed_search tools with
│                                @tool decorators. Provides build_hybrid_agent()
│                                factory for Phase 2 literature synthesis.
│
├── tools/                      Agent-callable tools:
│   ├── geo_tool.py             NCBI GEO search + metadata via E-utilities.
│   │                            search_geo() for multi-dataset queries,
│   │                            get_gse_metadata() for single-dataset detail.
│   │
│   ├── meta_analysis.py        Pure Python aggregation engine — organism counts,
│   │                            experiment types, platform usage, yearly timeline,
│   │                            sample count stats, title term extraction.
│   │                            Also builds LLM prompts for narrative generation.
│   │
│   ├── pubmed_tool.py          PubMed abstract search for additional context.
│   │
│   └── ontology_tool.py        Two-pass ontology mapper (CL, UBERON, EFO).
│                                Used for deep-dive analysis if needed.
│
├── rag/                        Retrieval-Augmented Generation components:
│   ├── ontology_loader.py      Downloads and parses CL, UBERON, EFO .obo files.
│   ├── vector_store.py         FAISS index for semantic ontology search.
│   └── term_normalizer.py      LLM-based disambiguation for ambiguous terms.
│
├── utils/                      Shared utilities:
│   ├── llm_client.py           Unified LLM interface — Ollama (GPU-local execution).
│   └── formatters.py           Output formatting for meta-analysis reports.
│
├── scripts/                    Setup and maintenance scripts:
│   ├── setup_ubuntu.sh         GPU/CUDA/venv/dependency setup.
│   ├── build_index.py          One-time ontology index builder.
│   └── smoke_test.py           End-to-end verification.
│
└── data/                       Generated data (not tracked in git):
    ├── ontologies/             Cached .obo files
    └── vector_store/           FAISS index + terms pickle
```

## Known Constraints

- **NCBI rate limits**: 3 req/s without a key, 10 req/s with one (free, instant
  signup at [ncbi.nlm.nih.gov/account](https://www.ncbi.nlm.nih.gov/account/)).
  Fetching 50 datasets will take ~17s without a key, ~5s with one.

- If **`gemma4:27b` is not supported** because it has 27B parameters which needs ~20 GB VRAM;
  but if a GPU has 8 GB VRAM. Use `medgemma:4b` (default) or `gemma2:9b` (upgrade).

## Declaration of Generative AI and AI-Assisted Technologies in the Project Preparation Process

Gemini 3.6 Flash and Claude Opus 4.6 were used for code review.
