"""Perplexity API integration for research-oriented queries.
    try:
        resp = requests.post(
            PERPLEXITY_URL,
            headers={
                "Authorization": f"Bearer {api_key}",  # guard: do not log key
                "Content-Type": "application/json",
            },
            data=json.dumps(payload),
            timeout=35,
        )
    except requests.RequestException as e:
        raise PerplexityError(f"Network error contacting Perplexity: {e}")
      endpoints; not implemented here).
"""
from __future__ import annotations

import os
import json
import requests
from typing import Any, Dict, Optional

PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"


class PerplexityError(RuntimeError):
    pass


def _clean_text(text: str) -> str:
    # Reuse existing markdown cleaner if available to keep consistency
    try:
        from .openrouter import clean_markdown_formatting  # type: ignore
        return clean_markdown_formatting(text)
    except Exception:
        return text


def _extract_text(resp_json: Dict[str, Any]) -> str:
    try:
        choices = resp_json.get("choices") or []
        if not choices:
            return "(no choices in response)"
        msg = choices[0].get("message", {})
        content = msg.get("content") or ""
        return _clean_text(content)
    except Exception as e:  # pragma: no cover - defensive
        return f"Failed to parse Perplexity response: {e}"


def generate_research_response(prompt: str, image_url: Optional[str] = None, temperature: float = 0.3) -> Dict[str, Any]:
    """Call Perplexity for research / academic style queries.

    Parameters
    ----------
    prompt: str
        User prompt (should already be validated upstream).
    image_url: Optional[str]
        Currently ignored; placeholder for future multimodal support.
    temperature: float
        Defaults lower for research for greater determinism.
    """
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        raise PerplexityError("PERPLEXITY_API_KEY not set")

    payload: Dict[str, Any] = {
        "model": os.getenv("PERPLEXITY_RESEARCH_MODEL", "sonar"),
        "messages": [
            {"role": "user", "content": prompt}
        ],
        # Keep tokens modest; can be overridden by model defaults
        "temperature": temperature,
    }

    # Optional: allow max tokens override
    max_tokens_env = os.getenv("PERPLEXITY_MAX_TOKENS")
    if max_tokens_env and max_tokens_env.isdigit():
        payload["max_tokens"] = int(max_tokens_env)

    try:
        resp = requests.post(
            PERPLEXITY_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            data=json.dumps(payload),
            timeout=35,
        )
    except requests.RequestException as e:
        raise PerplexityError(f"Network error contacting Perplexity: {e}")

    if resp.status_code != 200:
        # Keep a short snippet for diagnostics
        snippet = resp.text[:160].replace("\n", " ")
        raise PerplexityError(f"Perplexity HTTP {resp.status_code}: {snippet}")

    try:
        data = resp.json()
    except ValueError as e:
        raise PerplexityError(f"Invalid JSON from Perplexity: {e}")

    assistant_text = _extract_text(data)

    return {
        "model": data.get("model", payload["model"]),
        "task_type": "research",
        "assistant_text": assistant_text,
        "raw": data,
    }


if __name__ == "__main__":  # Simple local sanity check (does not call network if key missing)
    sample_prompt = "Write a research paper outline about transformer architectures with citations"
    from .openrouter import classify_task  # type: ignore
    print("Detected task:", classify_task(sample_prompt, None))
    if os.getenv("PERPLEXITY_API_KEY"):
        try:
            print("Invoking Perplexity (short test)...")
            result = generate_research_response(sample_prompt)
            print("Model:", result["model"])  # Avoid printing full raw
            print("Snippet:", result["assistant_text"][:200])
        except Exception as e:  # pragma: no cover
            print("Perplexity test failed:", e)
    else:
        print("PERPLEXITY_API_KEY not set; skipping live request.")
