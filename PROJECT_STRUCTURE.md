# GEO Meta-Analysis Toolkit: Exhaustive Codebase & Architecture Guide

This document provides an exhaustive, file-by-file technical manual of the GEO Meta-Analysis Toolkit. It details the exact architectural role, inner mechanics, parameters, dependencies, and execution flows of every folder and script in the repository.

---

## 🏛️ Root Directory

### `app.py`
* **Role:** The primary application entry point and interactive Streamlit UI dashboard.
* **UI Design & Aesthetics:**
  - **Sleek Glassmorphism:** Injects custom CSS utilizing dark-mode color palettes (`#0b0f19`), translucent glowing borders, and modern typography imported from Google Fonts (*Outfit*).
  - **Textured Background:** Applies a subtle radial mesh gradient (`rgba(167, 139, 250, 0.15)`) coupled with a geometric dark SVG pattern across the `.stApp` container.
  - **Distraction-Free Layout:** Features a massive glowing title (**🧬 GEO Meta-Analysis Toolkit**) and a full-width search input bar spanning 100% of the viewport container.
* **Unified 3-Phase Hybrid Pipeline Execution Sequence:**
  When a user enters a biomedical query and clicks **🚀 Run Meta-Analysis**, `app.py` executes an intelligent, zero-failure 3-phase sequence:
  1. **⚡ Phase 1 (Deterministic Foundation):**
     - Executes linear, non-agentic calls to `search_geo(clean_query, max_results=max_results)` and `analyze_metadata(datasets)`.
     - **Guarantee:** Within ~2 seconds, all series documents are fetched from Entrez E-utilities, natural language fallback expansion is triggered if strict queries return 0 hits, and all interactive charts (organism distributions, platform popularities, yearly trends) render immediately on screen.
  2. **🤖 Phase 2 (Autonomous Literature Synthesis):**
     - Injects pre-computed GEO aggregate statistics into a specialized LangChain ReAct Agent (`build_hybrid_agent`).
     - **Mechanism:** The AI agent autonomously formulates search queries against `pubmed_search_tool` to investigate published scientific abstracts explaining the biological mechanisms, disease context, and experimental protocols behind the fetched datasets.
  3. **🛡️ Phase 3 (Invisible Self-Healing):**
     - Traps execution inside a robust `try...except` block. If local GPU models (`medgemma:4b` on Ollama) get stuck during the ReAct reasoning loop, fail to format actions, or time out, `app.py` intercepts the exception invisibly.
     - **Auto-Degradation:** Instantly surfaces a toast notification (`⚠️ AI Agent loop timed out. Self-healing via linear prompt summarizer!`) and degrades to the linear prompt generator (`build_llm_summary_prompt` -> `llm.generate`) to guarantee a complete research landscape narrative on every run.

### `config.py`
* **Role:** Centralized static typing configuration and environment variable validation.
* **Mechanics:**
  - Built upon `pydantic-settings` (`BaseSettings`). Parses local `.env` files and exposes global singleton settings (`settings`).
  - **Key Tokens:** `NCBI_EMAIL` (mandatory for NCBI API compliance), `NCBI_API_KEY` (optional Entrez rate limit booster), `OLLAMA_MODEL` (default `medgemma:4b`), `GEO_SEARCH_MAX_RESULTS` (slider limits up to 10,000), `EMBED_BATCH_SIZE` (FAISS CUDA batching).

### `requirements.txt`
* **Role:** Python package dependency pinning.
* **Mechanics:** Specifies locked package versions for native Linux Ubuntu execution: `streamlit` (UI), `pydantic-settings` (config), `faiss-cpu` / `torch` / `sentence-transformers` (RAG semantic vector lookups), `langchain` / `langchain-community` (agentic reasoning), `requests` (NCBI REST API).

### `README.md`
* **Role:** Primary developer onboarding and system architecture guide.
* **Mechanics:** Contains full setup instructions for Ubuntu 24.04 with CUDA GPU drivers, detailed Mermaid diagrams of the unified hybrid execution engine, and usage tips for searching NCBI GEO.

### `PROJECT_STRUCTURE.md`
* **Role:** Living architectural code manual (this document).

### `.env` & `.env.example`
* **Role:** Local secret storage and Git-safe reference templates.
* **Mechanics:** `.env` stores private NCBI API keys and Entrez contact emails. `.env.example` serves as an unpopulated reference committed to version control.

### `.gitignore`
* **Role:** Git repository exclusion rules.
* **Mechanics:** Prevents committing virtual environments (`venv/`), Python cache files (`__pycache__/`), local `.env` secrets, and downloaded binary FAISS vector indexes (`data/`).

---

## 🤖 `agents/` — Autonomous Reasoning Layer

### `agents/__init__.py`
* **Role:** Package initialization. Exposes agent factory entry points.

### `agents/langchain_agent.py`
* **Role:** LangChain agent execution engine and shared tool state manager.
* **Mechanics:**
  - **Shared Memory State:** Maintains `_cached_datasets` list to allow zero-copy sharing of fetched series between Phase 1 linear analysis and Phase 2 agent tools.
  - **Tool Definitions:** Wraps `@tool` decorators for `geo_search_tool`, `metadata_analysis_tool`, and `pubmed_search_tool`.
  - **`build_hybrid_agent()`:** Factory function that constructs an `AgentExecutor` equipped exclusively with `pubmed_search_tool` (since GEO search is completed deterministically in Phase 1) with an 8-iteration safety cap.
  - **Local LLM Execution:** Uses local GPU/CPU inference via `Ollama` (`http://localhost:11434`) powered by `medgemma:4b` fine-tuned for biomedical domain tasks.

---

## 🛠️ `tools/` — Functional Execution Engine

### `tools/__init__.py`
* **Role:** Tool registry package initialization.

### `tools/geo_tool.py`
* **Role:** Core NCBI Gene Expression Omnibus (GEO) Entrez REST client.
* **Mechanics:**
  - **E-utilities Integration:** Queries `esearch.fcgi` (`db=gds`) to retrieve unique GEO Series (GSE) accessions, then batch-fetches document summaries from `esummary.fcgi`. Respects strict NCBI rate limits (3 req/sec unauthenticated, 10 req/sec authenticated via `NCBI_API_KEY`).
  - **Automatic Query Shorthand Expansion:** Translates biological abbreviations (e.g., expanding `"scRNA"` to `"(single cell RNA-seq OR scRNA-seq)"`).
  - **Resilient Fallback Search:** If strict SQL-like queries, spatial operators, or Boolean logic return 0 records, it automatically triggers `_clean_fallback_keywords()`. This strips bracketed field tags (`[Organism]`, `[Platform]`) and complex syntax to re-query NCBI GEO with clean natural language keywords.

### `tools/meta_analysis.py`
* **Role:** Statistical aggregation and narrative prompt engineering module.
* **Mechanics:**
  - **`analyze_metadata(datasets)`:** Iterates over fetched GSE document arrays to compute aggregate frequency distributions: top organisms, submission year trends, platform hardware popularities, sample count quantiles, and top title keyword clusters.
  - **`build_llm_summary_prompt(query, analysis)`:** Formulates a structured prompt translating computed statistical distributions into rigorous instructions for the LLM to compose a flowing prose research summary.

### `tools/pubmed_tool.py`
* **Role:** Scientific literature retrieval tool.
* **Mechanics:** Executes Entrez queries against PubMed (`db=pubmed`) to fetch top matching scientific abstracts. Used autonomously by hybrid agents in Phase 2 to cross-reference gene expression datasets with published clinical mechanisms.

### `tools/ontology_tool.py`
* **Role:** Biomedical controlled vocabulary mapping interface.
* **Mechanics:** Bridges raw, unstandardized sample characteristics (e.g., `"lung macrophage"`) to standardized ontology accessions (Cell Ontology `CL`, Uberon anatomical structures `UBERON`, Experimental Factor Ontology `EFO`) via FAISS similarity.

---

## 🧠 `rag/` — Retrieval-Augmented Generation & Semantic Search

### `rag/__init__.py`
* **Role:** RAG package initialization.

### `rag/vector_store.py`
* **Role:** High-speed FAISS flat L2 vector index manager.
* **Mechanics:**
  - Uses `torch` and `sentence-transformers/all-MiniLM-L6-v2` accelerated via native Linux CUDA drivers.
  - Indexes ~50,000 biomedical ontology terms into an in-memory `index.faiss` flat inner-product space, providing sub-50ms nearest-neighbor lookups.

### `rag/ontology_loader.py`
* **Role:** Raw OBO ontology ingestion engine.
* **Mechanics:** Streams `.obo` format ontology files directly from OBO Foundry repositories, parsing term IDs, names, synonyms, and definitions into clean serialized dictionaries.

### `rag/term_normalizer.py`
* **Role:** Two-pass semantic disambiguation engine.
* **Mechanics:** Combines high-speed FAISS vector similarity lookups with cost-gated local LLM reasoning (`ENABLE_TERM_NORMALIZATION`) to resolve ambiguous lab jargon into - **Local LLM Execution:** Uses local GPU inference via `Ollama` (`http://localhost:11434`) powered by `medgemma:4b` fine-tuned for biomedical domain tasks.

---

## ⚙️ `utils/` — Core Backend Infrastructure

### `utils/__init__.py`
* **Role:** Utilities package initialization.

### `utils/llm_client.py`
* **Role:** Low-level HTTP client wrapper providing a unified API interface for local LLM text generation and JSON decoding.
* **Mechanics:** Acts as a local inference client. Executes private local inference via `Ollama` (`medgemma:4b` on GPU).

### `utils/formatters.py`
* **Role:** Output formatting utility.
* **Mechanics:** Provides `pretty_json()` for human-readable JSON serialization of analysis results and API responses.

---

## 🖥️ `scripts/` — CLI Operations & Verification

### `scripts/__init__.py`
* **Role:** Scripts package initialization.

### `scripts/setup_ubuntu.sh`
* **Role:** Native Ubuntu 24.04 environment bootstrap script.
* **Mechanics:** Verifies NVIDIA CUDA GPU driver presence (`nvidia-smi`), creates Python virtual environments (`venv`), installs PyTorch with CUDA wheels, and verifies local Ollama model downloads.

### `scripts/build_index.py`
* **Role:** Offline RAG vector store compiler CLI.
* **Mechanics:** Command-line tool that downloads raw `.obo` ontologies and compiles the binary FAISS index in `data/vector_store/`.

### `scripts/smoke_test.py`
* **Role:** Automated end-to-end repository test suite.
* **Mechanics:** Executes headless integration checks against NCBI E-utilities, verifies FAISS vector store loading, and tests LLM generation without opening a browser GUI.
