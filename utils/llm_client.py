"""
utils/llm_client.py — Strict Local LLM abstraction layer.

Execution:
    100% Local GPU / CPU via Ollama (e.g. medgemma:4b natively via CUDA)

No online cloud APIs or external LLMs are used.
Streaming is supported for Ollama so the Streamlit UI can show
tokens as they arrive rather than waiting for the full response.
"""

import json
import requests
from typing import Generator, Optional

from config import settings


class LLMClient:
    """
    Thin wrapper over local Ollama API.

    Usage:
        from utils.llm_client import llm
        text = llm.generate("What is an alveolar macrophage?")
    """

    def __init__(self) -> None:
        # Cached after first health-check so we don't ping Ollama every call.
        self._ollama_up: Optional[bool] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> str:
        """Blocking generation via local Ollama. Returns complete response string."""
        self._require_ollama()
        return self._ollama_generate(prompt, system, max_tokens)

    def stream(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> Generator[str, None, None]:
        """
        Streaming generation via local Ollama. Yields token strings one by one.
        """
        self._require_ollama()
        yield from self._ollama_stream(prompt, system, max_tokens)

    def backend(self) -> str:
        """Returns 'ollama' or 'offline' — useful for UI status display."""
        return "ollama" if self._ollama_available() else "offline"

    def generate_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 300,
    ) -> dict:
        """
        Generation constrained to valid JSON output via native Ollama grammar constraint.

        Uses native format: "json" request field. Temperature is forced to 0.0
        since this is meant for extraction.
        """
        self._require_ollama()
        raw = self._ollama_generate_json(prompt, system, max_tokens)
        return json.loads(raw)

    # ── Ollama ────────────────────────────────────────────────────────────────

    def _require_ollama(self) -> None:
        if not self._ollama_available():
            raise RuntimeError(
                f"Local Ollama LLM service is unavailable at {settings.OLLAMA_BASE_URL}.\n"
                f"Please ensure Ollama is running and the model is pulled:\n"
                f"  ollama serve\n"
                f"  ollama pull {settings.OLLAMA_MODEL}"
            )

    def _ollama_available(self) -> bool:
        if self._ollama_up is None:
            try:
                r = requests.get(
                    f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=2
                )
                self._ollama_up = r.status_code == 200
            except Exception:
                self._ollama_up = False
        return self._ollama_up

    def _build_messages(
        self, prompt: str, system: Optional[str]
    ) -> list[dict]:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        return msgs

    def _ollama_generate(
        self, prompt: str, system: Optional[str], max_tokens: int
    ) -> str:
        resp = requests.post(
            f"{settings.OLLAMA_BASE_URL}/api/chat",
            json={
                "model": settings.OLLAMA_MODEL,
                "messages": self._build_messages(prompt, system),
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": 0.1,   # low temp → deterministic reasoning
                },
            },
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def _ollama_generate_json(
        self, prompt: str, system: Optional[str], max_tokens: int
    ) -> str:
        """
        Same as _ollama_generate but with format="json" grammar constraint.
        """
        resp = requests.post(
            f"{settings.OLLAMA_BASE_URL}/api/chat",
            json={
                "model": settings.OLLAMA_MODEL,
                "messages": self._build_messages(prompt, system),
                "stream": False,
                "format": "json",
                "options": {
                    "num_predict": max_tokens,
                    "temperature": 0.0,   # extraction task — no creativity wanted
                },
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def _ollama_stream(
        self, prompt: str, system: Optional[str], max_tokens: int
    ) -> Generator[str, None, None]:
        with requests.post(
            f"{settings.OLLAMA_BASE_URL}/api/chat",
            json={
                "model": settings.OLLAMA_MODEL,
                "messages": self._build_messages(prompt, system),
                "stream": True,
                "options": {"num_predict": max_tokens, "temperature": 0.1},
            },
            stream=True,
            timeout=180,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                token = chunk.get("message", {}).get("content", "")
                if token:
                    yield token
                if chunk.get("done"):
                    return


# ── Singleton ─────────────────────────────────────────────────────────────────
# Import this object everywhere:
#   from utils.llm_client import llm
llm = LLMClient()

