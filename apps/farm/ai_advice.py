"""Gemini AI plant advice for Mosquera Farm Log.

Calls the Google Gemini REST API (no extra packages, stdlib only) with a
prompt built from the plant's data, recent care logs, daily checks, and the
rain forecast. Fails soft: no key or no network returns a friendly message.
Get a free key at https://aistudio.google.com → Get API key.
"""

import json
import urllib.parse
import urllib.request

from django.conf import settings

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def is_configured() -> bool:
    return bool(getattr(settings, "GEMINI_API_KEY", ""))


def model_name() -> str:
    return getattr(settings, "GEMINI_MODEL", "gemini-flash-latest")


def build_prompt(plant, logs, checks, weather: dict) -> str:
    lines = [
        "You are a practical vegetable-gardening assistant for a small home farm in the Philippines.",
        f"Plant: {plant.name} ({plant.variety or 'unknown variety'}), status: {plant.get_status_display()}.",
        f"Planted {plant.planting_date}; expected harvest {plant.expected_harvest_date} "
        f"({plant.days_until_harvest} days away).",
        f"Water every {plant.water_every_days} day(s); fertilize every {plant.fertilize_every_days} day(s).",
    ]
    if weather.get("state") == "ok":
        lines.append(f"Rain forecast next 24h: {weather['rain_mm']} mm.")
    if logs:
        lines.append("Recent care history:")
        lines.extend(f"- [{log.get_category_display()} {log.date}] {log.description}" for log in logs[:5])
    if checks:
        lines.append("Recent daily checks:")
        for check in checks[:5]:
            lines.append(
                f"- {check.date}: health {check.get_health_display()}, "
                f"watered={check.watered}, fertilized={check.fertilized}, "
                f"height={check.height_cm or '?'}cm. {check.notes}".strip()
            )
    lines.append(
        "Give short, concrete advice (max 150 words): watering, fertilizing, "
        "and anything to watch for. Plain text, no markdown headings."
    )
    return "\n".join(lines)


def ask_gemini(prompt: str, timeout: int = 25) -> dict:
    """Ask Gemini; returns {"ok": True, "text": ...} or {"ok": False, "error": ...}."""
    if not is_configured():
        return {"ok": False, "error": "Set GEMINI_API_KEY to enable AI advice."}
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    url = f"{API_URL.format(model=urllib.parse.quote(model_name(), safe='-_.'))}?key={settings.GEMINI_API_KEY}"
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"ok": False, "error": f"Gemini request failed: {exc}"}
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError):
        return {"ok": False, "error": f"Unexpected Gemini response: {data}"}
    if not text:
        return {"ok": False, "error": "Gemini returned an empty answer."}
    return {"ok": True, "text": text}


def plant_advice(plant, logs, checks, weather: dict) -> dict:
    return ask_gemini(build_prompt(plant, logs, checks, weather))
