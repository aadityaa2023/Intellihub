from __future__ import annotations
import os
import json
import subprocess
import requests
from typing import Optional, Dict, Any


class LocalLLMError(RuntimeError):
    pass


def _detect_backend() -> Optional[str]:
    """Detect available local LLM backend.

    Priority:
      1. LOCAL_LLM_ENDPOINT (http(s) endpoint accepting POST {prompt})
      2. LOCAL_LLM_CMD (shell command that reads prompt from stdin)
      3. transformers pipeline if installed (checked at runtime)
    """
    if os.getenv("LOCAL_LLM_ENDPOINT"):
        return "endpoint"
    if os.getenv("LOCAL_LLM_CMD"):
        return "cmd"
    try:
        import transformers  # type: ignore
        return "transformers"
    except Exception:
        return None


def _call_endpoint(endpoint: str, prompt: str, temperature: float, timeout: int = 5) -> str:
    payload = {"prompt": prompt, "temperature": temperature}
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("LOCAL_LLM_ENDPOINT_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        raise LocalLLMError(f"Local endpoint request failed: {e}")
    if resp.status_code != 200:
        raise LocalLLMError(f"Local endpoint returned status {resp.status_code}: {resp.text[:200]}")
    try:
        data = resp.json()
    except Exception:
        # Some local services return plain text
        return resp.text
    # Accept common keys
    for key in ("text", "result", "response", "output"):
        if key in data:
            return data[key]
    # Fallback: stringify whole body
    return json.dumps(data)


def _call_cmd(cmd: str, prompt: str, timeout: int = 10) -> str:
    try:
        p = subprocess.run(cmd, input=prompt.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise LocalLLMError("Local LLM command timed out")
    if p.returncode != 0:
        stderr = (p.stderr.decode(errors="ignore") or "").strip()
        raise LocalLLMError(f"Local LLM command failed: {stderr}")
    return p.stdout.decode(errors="ignore")


def _call_transformers(prompt: str, temperature: float, max_new_tokens: int = 256) -> str:
    # Minimal safe import/use of transformers to avoid heavy dependencies unless available
    try:
        from transformers import pipeline
    except Exception as e:
        raise LocalLLMError(f"transformers not available: {e}")
    try:
        gen = pipeline("text-generation")
        out = gen(prompt, max_new_tokens=max_new_tokens, do_sample=True, temperature=float(temperature))
        if isinstance(out, list) and out:
            return out[0].get("generated_text", str(out[0]))
        return str(out)
    except Exception as e:
        raise LocalLLMError(f"transformers generation failed: {e}")


def generate_local_response(prompt: str, image_url: Optional[str] = None, temperature: float = 0.7) -> Dict[str, Any]:
    """Generate a response using a local LLM backend.

    Returns a dict compatible with other services:
      {"model": str, "task_type": str, "assistant_text": str, "raw": dict}
    """
    # Lazy import to avoid circular dependency at module import time
    task_type = "general"
    try:
        from .openrouter import classify_task
        task_type = classify_task(prompt, image_url)
    except Exception:
        pass

    backend = _detect_backend()
    if not backend:
        raise LocalLLMError("No local LLM backend detected. Set LOCAL_LLM_ENDPOINT or LOCAL_LLM_CMD or install transformers.")

    if backend == "endpoint":
        endpoint = os.getenv("LOCAL_LLM_ENDPOINT")
        model_name = f"local/endpoint:{endpoint}"
        text = _call_endpoint(endpoint, prompt, temperature)
        raw = {"backend": "endpoint", "url": endpoint}
    elif backend == "cmd":
        cmd = os.getenv("LOCAL_LLM_CMD")
        model_name = f"local/cmd:{cmd.split()[0] if cmd else 'cmd'}"
        text = _call_cmd(cmd, prompt)
        raw = {"backend": "cmd", "cmd": cmd}
    else:
        model_name = "local/transformers"
        text = _call_transformers(prompt, temperature)
        raw = {"backend": "transformers"}

    # Basic cleanup: prefer first line if very long models return whole JSON
    if isinstance(text, str):
        assistant_text = text.strip()
    else:
        assistant_text = str(text)

    return {"model": model_name, "task_type": task_type, "assistant_text": assistant_text, "raw": raw}
