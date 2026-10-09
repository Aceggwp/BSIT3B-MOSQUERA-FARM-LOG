"""OpenRouter AI backend for Mosquera Farm Log.

OpenRouter (https://openrouter.ai) exposes many models behind one
OpenAI-compatible endpoint. Stdlib only, fails soft like the Gemini backend.
Get a key at https://openrouter.ai/keys (free :free models available).
"""

import json
import urllib.request

from django.conf import settings

API_URL = "https://openrouter.ai/api/v1/chat/completions"


def is_configured() -> bool:
    return bool(getattr(settings, "OPENROUTER_API_KEY", ""))


def model_name() -> str:
    return getattr(settings, "OPENROUTER_MODEL", "google/gemma-4-31b-it:free")


def ask_openrouter(prompt: str, timeout: int = 30) -> dict:
    """Ask OpenRouter; returns {"ok": True, "text": ...} or {"ok": False, "error": ...}."""
    if not is_configured():
        return {"ok": False, "error": "Set OPENROUTER_API_KEY to enable AI advice."}
    body = json.dumps({
        "model": model_name(),
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    request = urllib.request.Request(
        API_URL, data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "HTTP-Referer": "http://localhost:8000/farm/",
            "X-Title": "Mosquera Farm Log",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"ok": False, "error": f"OpenRouter request failed: {exc}"}
    try:
        text = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        if isinstance(data, dict) and data.get("error"):
            return {"ok": False, "error": f"OpenRouter error: {data['error'].get('message', data['error'])}"}
        return {"ok": False, "error": f"Unexpected OpenRouter response: {data}"}
    if not text:
        return {"ok": False, "error": "OpenRouter returned an empty answer."}
    return {"ok": True, "text": text}
