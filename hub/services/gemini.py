
import os
import json
import requests
import time
from typing import Dict, Any, Optional, List, Tuple


class GeminiError(Exception):
    """Custom exception for Gemini API errors."""
    pass


def generate_gemini_response(
    prompt: str,
    image_url: Optional[str] = None,
    temperature: float = 0.7,
    model: str = "gemini-2.5-flash",
    use_new_key: bool = False
) -> Dict[str, Any]:
    """
    Generate response using Google Gemini API directly.
    
    Args:
        use_new_key: If True, use GEMINI_NEW_API_KEY instead of GEMINI_API_KEY
    
    Returns same shape as openrouter.generate_response() for compatibility:
    {
        "model": str,
        "task_type": str, 
        "assistant_text": str,
        "raw": dict
    }
    """
    # Use new API key if specified, otherwise fall back to regular key
    if use_new_key:
        api_key = os.getenv("GEMINI_NEW_API_KEY")
        if not api_key:
            # Fallback to regular key if new key not available
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise GeminiError("Neither GEMINI_NEW_API_KEY nor GEMINI_API_KEY found in environment")
    else:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise GeminiError("GEMINI_API_KEY not found in environment")
    
    # Allow environment override for default model selection (before task classification)
    # Support both legacy 1.5 and modern 2.5 defaults
    if model in ("gemini-1.5-flash", "gemini-2.5-flash"):
        env_model = os.getenv("GEMINI_MODEL") or os.getenv("INTELLIHUB_GEMINI_MODEL")
        if env_model:
            model = env_model.strip()

    # Detect task type using same logic as openrouter
    from .openrouter import classify_task
    task_type = classify_task(prompt, image_url)
    
    # Build request payload for Gemini API
    content_parts = [{"text": prompt}]
    
    # Add image if provided
    if image_url:
        try:
            # For Gemini, we need to fetch the image and encode it
            img_response = requests.get(image_url, timeout=10)
            img_response.raise_for_status()
            import base64
            img_b64 = base64.b64encode(img_response.content).decode()
            content_parts.append({
                "inline_data": {
                    "mime_type": img_response.headers.get("content-type", "image/jpeg"),
                    "data": img_b64
                }
            })
        except Exception as e:
            raise GeminiError(f"Failed to fetch image for Gemini: {e}")
    
    payload = {
        "contents": [{
            "parts": content_parts
        }],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 2048,
            "topP": 0.95,
            "topK": 40
        }
    }
    
    # Gemini API endpoint
    # Updated alternates based on actual available models (as of Oct 2025)
    # Priority: 2.5 > 2.0 > legacy aliases
    alternates_map: Dict[str, List[str]] = {
        "gemini-1.5-flash": [
            "gemini-2.5-flash",
            "gemini-flash-latest",
            "gemini-2.0-flash",
            "gemini-2.0-flash-001",
        ],
        "gemini-1.5-pro": [
            "gemini-2.5-pro",
            "gemini-pro-latest",
            "gemini-2.0-pro-exp",
        ],
        "gemini-2.5-flash": [
            "gemini-flash-latest",
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash",
        ],
        "gemini-2.5-pro": [
            "gemini-pro-latest",
            "gemini-2.5-flash",
        ],
    }

    attempted: List[str] = []
    candidate_models: List[str] = []
    candidate_models.append(model)
    if model in alternates_map:
        candidate_models.extend([m for m in alternates_map[model] if m != model])

    last_error: Optional[str] = None
    # Reuse cached model list if present (timestamp, list)
    cache: Tuple[float, List[str]] | None = getattr(generate_gemini_response, "_model_list_cache", None)  # type: ignore
    for candidate in list(candidate_models):  # iterate over a snapshot; we may append dynamically
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{candidate}:generateContent"
        try:
            response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                params={"key": api_key},
                json=payload,
                timeout=30
            )
        except requests.RequestException as e:
            last_error = f"Network error: {e}"
            continue

        if response.status_code == 200:
            try:
                data = response.json()
            except ValueError:
                raise GeminiError("Gemini returned non-JSON 200 response")
            assistant_text = extract_gemini_text(data)
            from .openrouter import clean_markdown_formatting  # local import
            cleaned_text = clean_markdown_formatting(assistant_text)
            return {
                "model": f"gemini/{candidate}",
                "task_type": task_type,
                "assistant_text": cleaned_text,
                "raw": data
            }

        # 404 model not found -> try alternate if available
        snippet = response.text[:200].replace('\n', ' ')
        last_error = f"HTTP {response.status_code} {snippet}" if snippet else f"HTTP {response.status_code}"
        if response.status_code == 404:
            attempted.append(candidate)
            # Dynamic discovery: only perform once per run or every 5 minutes
            now = time.time()
            model_list: List[str] = []
            if not cache or (now - cache[0] > 300):
                try:
                    list_resp = requests.get(
                        "https://generativelanguage.googleapis.com/v1beta/models",
                        params={"key": api_key}, timeout=15
                    )
                    if list_resp.status_code == 200:
                        listing = list_resp.json()
                        model_list = [m.get("name", "") for m in listing.get("models", []) if m.get("name")]
                        generate_gemini_response._model_list_cache = (now, model_list)  # type: ignore
                        cache = (now, model_list)
                except Exception:
                    model_list = []
            else:
                model_list = cache[1]

            preferred = os.getenv("GEMINI_PREFERRED_FAMILY", "gemini-2.5")
            # Pick first model containing preferred token that we haven't tried
            dynamic_pick_full = next((m for m in model_list if preferred in m), None)
            if dynamic_pick_full:
                dynamic_short = dynamic_pick_full.split('/')[-1]
                if dynamic_short not in candidate_models:
                    candidate_models.append(dynamic_short)
                    # Add to iteration by continuing (loop will include newly appended at end)
            continue
        # For other errors (401, 429, 5xx) break early - no alternate likely to help
        break

    raise GeminiError(
        "Gemini API failed after trying models="
        f"{candidate_models} last_error={last_error}. "
        "Set GEMINI_MODEL or GEMINI_PREFERRED_FAMILY to override."
    )


def extract_gemini_text(data: Dict[str, Any]) -> str:
    """Extract text content from Gemini API response."""
    try:
        candidates = data.get("candidates", [])
        if not candidates:
            return "(no candidates in Gemini response)"
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if not parts:
            return "(no parts in Gemini response)"
        text_parts = [p["text"] for p in parts if isinstance(p, dict) and p.get("text")]
        return "\n".join(text_parts) if text_parts else "(no text parts in Gemini response)"
    except Exception as e:  # pragma: no cover - defensive
        return f"Failed to parse Gemini response: {e}"