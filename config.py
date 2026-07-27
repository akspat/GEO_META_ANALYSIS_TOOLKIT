"""
config.py — Centralised application settings via pydantic-settings.

All values are read from .env (copy .env.example → .env and fill in).

Ollama model VRAM budget (Q4_K_M quantisation on 8 GB vRAM GPU):
    medgemma:4b  →  ~3.5 GB   ← default  (bio-focused, fits with headroom)
    gemma2:9b    →  ~5.5 GB   ← upgrade  (better reasoning, still fits)
    llama3.1:8b  →  ~4.9 GB   ← alt      (strong general purpose)
    gemma4:27b   →  ~18 GB    ← requires cloud GPU, does not fit 8 GB VRAM
"""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM ──────────────────────────────────────────────────────────────────
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    # Pull with: ollama pull medgemma:4b
    # Upgrade:   ollama pull gemma2:9b
    OLLAMA_MODEL: str = "medgemma:4b"

    # ── NCBI API ──────────────────────────────────────────────────────────────
    # Free key → 10 req/s instead of 3 req/s.
    # Register: https://www.ncbi.nlm.nih.gov/account/
    NCBI_API_KEY: Optional[str] = None
    # NCBI Terms of Service require a valid email.
    NCBI_EMAIL: str = "your_email@example.com"

    # ── Storage ────────────────────────────────────────────────────────────────
    VECTOR_STORE_PATH: str = "./data/vector_store"
    ONTOLOGY_DATA_PATH: str = "./data/ontologies"

    # ── Agent behaviour ────────────────────────────────────────────────────────
    # Below this cosine similarity the agent must call PubMed before retrying.
    ONTOLOGY_CONFIDENCE_THRESHOLD: float = 0.70
    AGENT_MAX_STEPS: int = 15

    # ── GEO Search ─────────────────────────────────────────────────────────────
    # Max datasets to fetch per search query. Higher = slower (NCBI rate limits).
    GEO_SEARCH_MAX_RESULTS: int = 20

    # LLM-assisted term disambiguation (e.g. "macs" = MACS-isolation METHOD
    # vs. slang for "macrophages" CELL TYPE — pure embedding similarity can't
    # tell these apart, an LLM with field context can).
    #
    # COST-GATED BY DESIGN: this only fires when a raw embedding lookup is
    # ALREADY below threshold (see tools/ontology_tool.py). Clean terms never
    # pay the extra LLM round-trip. Disable if you want zero LLM calls during
    # ontology lookup (faster, but ambiguous jargon will stay unresolved).
    ENABLE_TERM_NORMALIZATION: bool = True

    # ── Embeddings ─────────────────────────────────────────────────────────────
    # Batch size for sentence-transformers on 8 GB VRAM GPU.
    # Reduce to 256 if you see CUDA OOM errors.
    EMBED_BATCH_SIZE: int = 512

    # ── App ────────────────────────────────────────────────────────────────────
    APP_TITLE: str = "GEO Meta-Analysis Toolkit"
    DEBUG: bool = False


# Module-level singleton — import this everywhere:
#   from config import settings
settings = Settings()
