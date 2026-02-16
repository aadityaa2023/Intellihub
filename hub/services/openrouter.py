from __future__ import annotations
import os
import json
import time
import hashlib
from typing import List, Dict, Any, Optional
import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Simple in-memory cache for responses (use Redis in production)
_response_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL = 300  # 5 minutes

# Simple in-process metrics for operational visibility (reset on process restart)
_metrics = {
    'attempts': 0,
    'successful_calls': 0,
    'errors_total': 0,
    'bytes_received': 0,
    'last_latency_ms': 0,
}

# Attempt to load .env early if python-dotenv is installed
try:  # lightweight optional dependency already in requirements
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

# Basic model registry: map task type to preferred model(s) with fallbacks
MODEL_PREFERENCES = {
    # Updated Gemini identifiers with -latest suffix (older names may 400/404)
    # Environment overrides available: INTELLIHUB_MODEL_CODE, _GENERAL, _IMAGE, _RESEARCH
    "code": [
        os.getenv("INTELLIHUB_MODEL_CODE", "google/gemini-1.5-flash-latest"),
        "qwen/qwen-2.5-coder-32b-instruct:free",
        "qwen/qwen-2.5-72b-instruct:free",
    ],
    "image_reason": [
        os.getenv("INTELLIHUB_MODEL_IMAGE", "google/gemini-1.5-pro-latest"),
        "x-ai/grok-4-fast:free",
        "qwen/qwen-2.5-72b-instruct:free",
    ],
    "general": [
        os.getenv("INTELLIHUB_MODEL_GENERAL", "google/gemini-1.5-flash-latest"),
        "qwen/qwen-2.5-72b-instruct:free",
        "qwen/qwen-2.5-coder-32b-instruct:free",
    ],
    "research": [
        os.getenv("INTELLIHUB_MODEL_RESEARCH", "google/gemini-1.5-pro-latest"),
        "qwen/qwen-2.5-72b-instruct:free",
        "qwen/qwen-2.5-coder-32b-instruct:free",
    ],
}

DEFAULT_FALLBACK_MODEL = "qwen/qwen-2.5-72b-instruct:free"


class RateLimitExhaustedError(RuntimeError):
    """Raised when every attempt across keys/models ended in rate limiting (429)."""
    pass

def collect_api_keys() -> List[str]:
    """Collect OpenRouter API keys from environment with precedence.

    Precedence / sources:
        1. OPENROUTER_API_KEYS (comma separated)
        2. OPENROUTER_API_KEY_1..N (indexed)
        3. Legacy variable names (deepseek_api_key, grok_api_key) for backward compatibility.
    
    Note: GEMINI_API_KEY is intentionally excluded - it's used for direct Gemini fallback only.
    Duplicates are removed preserving order.
    """
    keys: List[str] = []
    csv = os.getenv("OPENROUTER_API_KEYS")
    if csv:
        keys.extend([k.strip() for k in csv.split(',') if k.strip()])
    idx = 1
    while True:
        val = os.getenv(f"OPENROUTER_API_KEY_{idx}")
        if not val:
            break
        keys.append(val.strip())
        idx += 1
    # Legacy keys (excluding GEMINI_API_KEY which is for direct Gemini only)
    for legacy in ["deepseek_api_key", "grok_api_key"]:
        lv = os.getenv(legacy)
        if lv:
            keys.append(lv.strip())
    seen = set()
    uniq: List[str] = []
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            uniq.append(k)
    if not uniq:
        # Helpful one-time debug hint (doesn't raise here; caller handles empty case)
        if os.getenv("OPENROUTER_API_KEYS") is None:
            # Provide guidance for user debugging
            print("[IntelliHub] No OPENROUTER_API_KEYS found in environment. Ensure .env is loaded or variables exported.")
    return uniq


def classify_task(prompt: str, image_url: Optional[str]) -> str:
    """Naive heuristic classifier. Expanded with research detection.

    Order matters: research before code to avoid misclassification of
    prompts like "research paper about python algorithms".
    """
    p = prompt.lower()
    # Detect research / academic intents
    research_terms = [
        "research", "literature review", "academic", "paper", "survey", "citation",
        "references", "doi", "scholarly", "journal", "systematic review"
    ]
    if any(term in p for term in research_terms):
        return "research"
    if any(word in p for word in ["code", "function", "bug", "python", "javascript", "algorithm"]):
        return "code"
    if image_url:
        return "image_reason"
    return "general"


def pick_model(task_type: str) -> str:
    models = MODEL_PREFERENCES.get(task_type) or []
    if models:
        return models[0]
    return DEFAULT_FALLBACK_MODEL


def try_models_with_fallback(models: List[str], payload: Dict[str, Any], api_keys: List[str]) -> Dict[str, Any]:
    """Try multiple models in sequence until one succeeds.

    If all failures appear to be pure 429 rate limits, raise RateLimitExhaustedError
    so the caller can present a friendly message instead of a generic 500.
    """
    last_error = None
    all_attempts: list[str] = []
    rate_limit_only = True
    for model in models:
        payload_copy = payload.copy()
        payload_copy["model"] = model
        try:
            return request_with_rotation(payload_copy, api_keys, max_retries_per_key=1, backoff_seconds=5)
        except RuntimeError as e:
            err_text = str(e)
            last_error = err_text
            all_attempts.append(err_text)
            # Determine if this error contained any non-429 signals
            if "429" not in err_text:
                rate_limit_only = False
            # If it's a rate limit error, try next model immediately
            if "429" in err_text and len(models) > 1:
                print(f"[IntelliHub] Model {model} rate-limited, trying fallback...")
                continue
            # For other errors, propagate immediately
            raise
    # If all models failed
    if rate_limit_only and last_error and "429" in last_error:
        raise RateLimitExhaustedError("All models/keys hit external 429 rate limits.")
    raise RuntimeError(f"All fallback models failed. Last error: {last_error}")


def build_messages(prompt: str, image_url: Optional[str]) -> List[Dict[str, Any]]:
    if image_url:
        return [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ]
    return [{"role": "user", "content": prompt}]


def request_with_rotation(payload: Dict[str, Any], api_keys: List[str], max_retries_per_key: int = 2, backoff_seconds: int = 5) -> Dict[str, Any]:
    if not api_keys:
        raise RuntimeError("No API keys found. Set OPENROUTER_API_KEYS or OPENROUTER_API_KEY_1.")

    debug = os.getenv("INTELLIHUB_DEBUG") == "1"
    referer = os.getenv("INTELLIHUB_REFERER")
    title = os.getenv("INTELLIHUB_TITLE")

    base_headers = {
        "Content-Type": "application/json",
    }
    if referer:
        base_headers["HTTP-Referer"] = referer
    if title:
        base_headers["X-Title"] = title

    last_error: Optional[str] = None
    attempts_summary: List[str] = []

    for key_index, key in enumerate(api_keys):
        for attempt in range(1, max_retries_per_key + 1):
            try:
                _metrics['attempts'] += 1
                import time as _time
                start = _time.time()
                resp = requests.post(
                    url=OPENROUTER_URL,
                    headers={
                        **base_headers,
                        "Authorization": f"Bearer {key}",
                    },
                    data=json.dumps(payload),
                    timeout=20,  # Reduced from 60s for faster response
                )
                latency_ms = int((_time.time() - start) * 1000)
                _metrics['last_latency_ms'] = latency_ms
            except requests.RequestException as e:
                last_error = f"Network error (key {key_index+1}, attempt {attempt}): {e}"
                attempts_summary.append(last_error)
                if debug:
                    print("[IntelliHub]", last_error)
                time.sleep(backoff_seconds)
                continue

            status = resp.status_code
            snippet = resp.text[:180].replace('\n', ' ')
            attempts_summary.append(f"key {key_index+1} attempt {attempt} -> {status} : {snippet}")
            if debug:
                print(f"[IntelliHub] key {key_index+1} attempt {attempt} status {status}")

            if status == 200:
                try:
                    data = resp.json()
                    _metrics['successful_calls'] += 1
                    try:
                        _metrics['bytes_received'] += len(resp.content)
                    except Exception:
                        pass
                    return data
                except ValueError:
                    raise RuntimeError("Response not valid JSON (200)")
            if status in (401, 403):  # auth problems -> rotate to next key
                last_error = f"Auth error {status} with key {key_index+1}"
                break
            if status == 429:  # rate limit -> retry same key with longer backoff
                backoff_time = backoff_seconds * (2 ** (attempt - 1))  # exponential backoff
                if debug:
                    print(f"[IntelliHub] rate limited key {key_index+1}, backing off {backoff_time}s")
                time.sleep(backoff_time)
                continue
            # Other status codes -> rotate
            last_error = f"HTTP {status} with key {key_index+1}"
            break

    diagnostic = " | ".join(attempts_summary)
    _metrics['errors_total'] += 1
    # If every attempt line appears to be 429 rate limiting, surface specialized error
    if diagnostic and all(" 429 " in a or "429" in a for a in attempts_summary):
        raise RateLimitExhaustedError(f"Rate limited across all keys. Attempts: {diagnostic}")
    raise RuntimeError(f"All keys failed. Last error: {last_error}. Attempts: {diagnostic}")


def get_metrics() -> Dict[str, Any]:
    """Return a snapshot of in-process metrics."""
    return dict(_metrics)


def extract_assistant_text(result: Dict[str, Any]) -> str:
    try:
        choices = result.get("choices") or []
        if not choices:
            return "(no choices in response)"
        msg = choices[0].get("message", {})
        content = msg.get("content")
        if isinstance(content, list):
            text_parts = [c.get("text") for c in content if isinstance(c, dict) and c.get("type") == "text"]
            raw_text = "\n".join(filter(None, text_parts)) or "(no text parts)"
        else:
            raw_text = content or "(empty content)"
        
        # Clean up markdown formatting to make it more conversational like ChatGPT
        cleaned_text = clean_markdown_formatting(raw_text)
        return cleaned_text
    except Exception as e:
        return f"Failed to parse response: {e}"


def clean_markdown_formatting(text: str) -> str:
    """Format text like professional chat UIs - preserve structure but clean presentation.
    
    Instead of removing all formatting, we:
    - Keep meaningful structure (headers, lists, code blocks)
    - Convert markdown to clean, readable plain text with proper spacing
    - Preserve bullets and numbering in a readable way
    """
    if not text:
        return text
    
    import re
    
    # Preserve code blocks first (don't process their content)
    code_blocks = []
    def save_code_block(match):
        code_blocks.append(match.group(0))
        return f"___CODE_BLOCK_{len(code_blocks)-1}___"
    
    text = re.sub(r'```[\s\S]*?```', save_code_block, text)
    text = re.sub(r'`[^`]+`', save_code_block, text)
    
    # Convert headers to bold text with spacing
    text = re.sub(r'^#{1,6}\s+(.+)$', r'\n\1\n', text, flags=re.MULTILINE)
    
    # Convert bold/italic to plain (keep text, remove markers)
    text = re.sub(r'\*\*\*([^*]+)\*\*\*', r'\1', text)  # bold+italic
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)      # bold
    text = re.sub(r'\*([^*]+)\*', r'\1', text)          # italic
    text = re.sub(r'__([^_]+)__', r'\1', text)          # bold alt
    text = re.sub(r'_([^_]+)_', r'\1', text)            # italic alt
    
    # Convert bullet points to clean bullets with proper indentation
    text = re.sub(r'^[\s]*[-•*]\s+', '• ', text, flags=re.MULTILINE)
    
    # Convert numbered lists to clean format
    text = re.sub(r'^[\s]*(\d+)\.\s+', r'\1. ', text, flags=re.MULTILINE)
    
    # Clean up excessive line breaks (max 2 consecutive)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Restore code blocks
    for i, block in enumerate(code_blocks):
        text = text.replace(f"___CODE_BLOCK_{i}___", block)
    
    # Clean up spaces and normalize whitespace
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        # Keep line if it has content or is a spacing line between paragraphs
        stripped = line.strip()
        if stripped or (cleaned_lines and cleaned_lines[-1].strip()):
            cleaned_lines.append(line.rstrip())
    
    # Remove leading/trailing empty lines
    while cleaned_lines and not cleaned_lines[0].strip():
        cleaned_lines.pop(0)
    while cleaned_lines and not cleaned_lines[-1].strip():
        cleaned_lines.pop()
    
    return '\n'.join(cleaned_lines)


def generate_cache_key(prompt: str, image_url: Optional[str], task_type: str) -> str:
    """Generate cache key for response caching"""
    cache_input = f"{prompt}|{image_url or ''}|{task_type}"
    return hashlib.md5(cache_input.encode()).hexdigest()


def get_cached_response(cache_key: str) -> Optional[Dict[str, Any]]:
    """Get cached response if not expired"""
    if cache_key in _response_cache:
        cached = _response_cache[cache_key]
        if time.time() - cached['timestamp'] < CACHE_TTL:
            return cached['response']
        else:
            # Remove expired cache
            del _response_cache[cache_key]
    return None


def cache_response(cache_key: str, response: Dict[str, Any]) -> None:
    """Cache response with timestamp"""
    _response_cache[cache_key] = {
        'response': response,
        'timestamp': time.time()
    }


def generate_response(prompt: str, image_url: Optional[str] = None, temperature: float = 0.7) -> Dict[str, Any]:
    task_type = classify_task(prompt, image_url)

    cache_key = generate_cache_key(prompt, image_url, task_type)
    cached = get_cached_response(cache_key)
    if cached:
        return cached

    # Special dispatch: research -> Perplexity if key present
    if task_type == "research" and os.getenv("PERPLEXITY_API_KEY"):
        try:
            from .perplexity import generate_research_response  # local import to avoid hard dependency if unused
            research_result = generate_research_response(prompt=prompt, image_url=image_url, temperature=min(temperature, 0.5))
            cache_response(cache_key, research_result)
            return research_result
        except Exception as e:
            # Fall through to OpenRouter fallback models
            print(f"[IntelliHub] Perplexity research path failed: {e}. Falling back to OpenRouter models.")

    models = MODEL_PREFERENCES.get(task_type) or [DEFAULT_FALLBACK_MODEL]
    api_keys = collect_api_keys()
    messages = build_messages(prompt, image_url)
    payload = {"model": models[0], "messages": messages, "temperature": temperature}

    # If no OpenRouter keys available but GEMINI_API_KEY exists, use direct Gemini
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not api_keys and gemini_key:
        try:
            from .gemini import generate_gemini_response
            print("[IntelliHub] No OpenRouter keys found, using direct Gemini API...")
            direct = generate_gemini_response(prompt=prompt, image_url=image_url, temperature=temperature)
            cache_response(cache_key, direct)
            return direct
        except Exception as gemini_direct_error:  # pragma: no cover - defensive
            raise RuntimeError(f"No OpenRouter keys and Gemini direct failed: {gemini_direct_error}")

    try:
        raw = try_models_with_fallback(models, payload, api_keys)
        model_used = raw.get("model", models[0])
    except RateLimitExhaustedError:
        # Return a friendly structured message instead of raising
        guidance = (
            "The service hit external rate limits on all available providers.\n\n"
            "What you can do now:\n"
            "• Add credits to OpenRouter (unlocks higher daily quota).\n"
            "• Add additional API keys (OPENROUTER_API_KEYS) for rotation.\n"
            "• Retry in a few minutes (limits reset periodically).\n"
            "• Upgrade to paid / non-free models and include them in MODEL_PREFERENCES.\n"
            "• Implement per-user throttling to reduce burst traffic."
        )
        return {
            "model": models[0],
            "task_type": task_type,
            "assistant_text": guidance,
            "raw": {"error": "rate_limited"}
        }
    except RuntimeError as e:
        # Attempt final OpenRouter default model first
        try:
            payload["model"] = DEFAULT_FALLBACK_MODEL
            raw = request_with_rotation(payload, api_keys, max_retries_per_key=1, backoff_seconds=8)
            model_used = DEFAULT_FALLBACK_MODEL
        except Exception as final_openrouter_error:  # pragma: no cover - defensive
            # If Gemini fallback is explicitly disabled, re-raise
            if os.getenv("INTELLIHUB_DISABLE_GEMINI_FALLBACK") == "1":
                raise final_openrouter_error

            # First try a local LLM fallback if configured. Local LLMs are usually fastest
            # and can return a quick response when external providers are down or slow.
            try:
                from .local_llm import generate_local_response  # optional local backend
                print("[IntelliHub] OpenRouter failed; attempting local LLM fallback...")
                local_result = generate_local_response(prompt=prompt, image_url=image_url, temperature=temperature)
                cache_response(cache_key, local_result)
                return local_result
            except Exception as local_err:
                # Log and continue to Gemini fallback (if available)
                print(f"[IntelliHub] Local LLM fallback failed: {local_err}")

            # If local attempt didn't work, attempt Gemini direct API if key present
            gemini_key = os.getenv("GEMINI_API_KEY")
            if gemini_key:
                try:
                    from .gemini import generate_gemini_response  # local import to avoid mandatory dependency
                    print("[IntelliHub] OpenRouter failed; attempting Gemini direct fallback...")
                    gemini_result = generate_gemini_response(prompt=prompt, image_url=image_url, temperature=temperature)
                    cache_response(cache_key, gemini_result)
                    return gemini_result
                except Exception as gemini_err:  # If Gemini also fails, surface combined error
                    raise RuntimeError(f"OpenRouter failed ({e}); Gemini fallback failed ({gemini_err})")
            # No Gemini key or disabled fallback; re-raise original
            raise final_openrouter_error

    assistant_text = extract_assistant_text(raw)
    result = {"model": model_used, "task_type": task_type, "assistant_text": assistant_text, "raw": raw}
    cache_response(cache_key, result)
    return result
