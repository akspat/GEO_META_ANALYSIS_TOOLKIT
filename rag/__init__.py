"""
rag — Retrieval-Augmented Generation components for ontology term matching.

Handles the full RAG pipeline from raw ontology data to semantic search:
    - ontology_loader:   Downloads and parses CL, UBERON, EFO .obo files
    - vector_store:      FAISS index over sentence-transformer embeddings
    - term_normalizer:   Optional LLM-based disambiguation for ambiguous terms
"""
