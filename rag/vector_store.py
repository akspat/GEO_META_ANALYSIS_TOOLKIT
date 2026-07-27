"""
rag/vector_store.py — FAISS-backed semantic search over ontology terms.

Embedding model: all-MiniLM-L6-v2 (sentence-transformers)
    Dimension:  384
    GPU:        Yes — sentence-transformers uses PyTorch CUDA automatically.
                An 8 GB VRAM GPU will be detected and used automatically via CUDA.
    Download:   ~90 MB, cached in ~/.cache/huggingface/ after first run.

FAISS index: IndexFlatIP  (exact inner-product = cosine after L2 normalisation)
    Why exact? Our corpus is ~50k terms — approximate indices give no
    speed benefit below ~1M vectors but add complexity.

Build time on 8 GB VRAM GPU (batch 512):  ~10–15 min for ~50k terms.
Load time (from disk):                < 1 second.
Query time:                           < 50 ms.
"""

import pickle
import numpy as np
from pathlib import Path
from typing import Optional

from config import settings

# ── Lazy globals (avoid slow imports at module load) ──────────────────────────
_faiss = None
_model = None


def _get_faiss():
    global _faiss
    if _faiss is None:
        import faiss
        _faiss = faiss
    return _faiss


def _get_model():
    """
    Load SentenceTransformer model.
    Automatically uses GPU if CUDA is available natively.
    """
    global _model
    if _model is None:
        import torch
        from sentence_transformers import SentenceTransformer

        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"  [Embeddings] Device: {device.upper()}", end="")
        if device == "cuda":
            gpu = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / 1e9
            print(f"  ({gpu}, {vram:.1f} GB)", end="")
        print()

        _model = SentenceTransformer("all-MiniLM-L6-v2", device=device)
    return _model


# ── Vector store class ────────────────────────────────────────────────────────

class OntologyVectorStore:
    """
    Semantic search over ontology terms.

    Typical workflow:
        # First time only (runs in build_index.py):
        store = OntologyVectorStore()
        store.build(terms)          # downloads model, embeds all terms, saves index

        # Every subsequent run (fast):
        store = OntologyVectorStore()
        store.load()                # reads index.faiss + terms.pkl from disk
        results = store.search("lung macrophage", top_k=5)
    """

    DIMENSION = 384  # all-MiniLM-L6-v2 output dimensionality

    def __init__(self, store_path: str | None = None) -> None:
        self.store_path = Path(store_path or settings.VECTOR_STORE_PATH)
        self.index: Optional[object] = None
        self.terms: list[dict] = []

    # ── Build ─────────────────────────────────────────────────────────────────

    def build(self, terms: list[dict]) -> None:
        """
        Embed all term texts and build the FAISS index.

        Args:
            terms: List of dicts, each must have an 'embed_text' field.

        The batch_size=512 is tuned for 8 GB VRAM GPUs.
        Reduce to 256 if you see CUDA OOM errors.
        """
        faiss = _get_faiss()
        model = _get_model()

        print(f"\n  Embedding {len(terms):,} terms ...")
        texts = [t["embed_text"] for t in terms]

        embeddings = model.encode(
            texts,
            batch_size=settings.EMBED_BATCH_SIZE,
            show_progress_bar=True,
            normalize_embeddings=True,   # L2 normalise → cosine sim = dot product
            convert_to_numpy=True,
        )
        embeddings = np.asarray(embeddings, dtype=np.float32)

        # Build index
        self.index = faiss.IndexFlatIP(self.DIMENSION)
        self.index.add(embeddings)
        self.terms = terms

        print(f"  Index ready: {self.index.ntotal:,} vectors")
        self._save()

    # ── Persist ───────────────────────────────────────────────────────────────

    def _save(self) -> None:
        """Write index and term metadata to disk."""
        faiss = _get_faiss()
        self.store_path.mkdir(parents=True, exist_ok=True)

        faiss.write_index(self.index, str(self.store_path / "index.faiss"))
        with open(self.store_path / "terms.pkl", "wb") as f:
            pickle.dump(self.terms, f)

        print(f"  Saved to {self.store_path}/")

    def load(self) -> bool:
        """
        Load a pre-built index from disk.
        Returns True on success, False if files don't exist yet.
        """
        faiss = _get_faiss()
        idx_path = self.store_path / "index.faiss"
        pkl_path = self.store_path / "terms.pkl"

        if not idx_path.exists() or not pkl_path.exists():
            return False

        self.index = faiss.read_index(str(idx_path))
        with open(pkl_path, "rb") as f:
            self.terms = pickle.load(f)

        print(f"  Loaded index: {self.index.ntotal:,} vectors from {self.store_path}/")
        return True

    # ── Query ─────────────────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """
        Semantic search.  Returns top_k ontology terms by cosine similarity.

        Args:
            query:  Raw biological term, e.g. "lung macs" or "NSCLC cells"
            top_k:  Number of results to return

        Returns:
            List of term dicts, each augmented with a 'score' key (0.0–1.0).
            Higher score = closer semantic match.
        """
        if self.index is None:
            raise RuntimeError(
                "Vector store not initialised.\n"
                "Run:  python scripts/build_index.py"
            )

        faiss = _get_faiss()
        model = _get_model()

        q_vec = model.encode(
            [query],
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        q_vec = np.asarray(q_vec, dtype=np.float32)

        scores, indices = self.index.search(q_vec, top_k)

        results: list[dict] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:          # FAISS returns -1 when fewer results than top_k
                continue
            term = dict(self.terms[idx])
            term["score"] = float(score)
            results.append(term)

        return results
