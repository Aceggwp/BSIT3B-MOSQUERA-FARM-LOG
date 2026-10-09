"""Weather-adaptive reminders for Mosquera Farm Log.

Default provider is Open-Meteo (https://open-meteo.com) — free, no API key
or signup. OpenWeatherMap remains available via
FARM_WEATHER_PROVIDER=openweathermap (needs OPENWEATHER_API_KEY).

Both paths fail soft: no network means the farm behaves as before.
"""

import json
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

from django.conf import settings
from django.core.cache import caches

OWM_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OWM_CACHE_KEY = "farm:weather:owm"
METEO_CACHE_KEY = "farm:weather:openmeteo"


def provider() -> str:
    return getattr(settings, "FARM_WEATHER_PROVIDER", "open-meteo")


def fetch_open_meteo(timeout: int = 6) -> dict | None:
    """Hourly precipitation for the next 2 days (UTC). Cached, None on failure."""
    cache = caches["default"]
    cached = cache.get(METEO_CACHE_KEY)
    if cached is not None:
        return cached
    params = urllib.parse.urlencode({
        "latitude": settings.FARM_WEATHER_LAT,
        "longitude": settings.FARM_WEATHER_LON,
        "hourly": "precipitation",
        "timezone": "UTC",
        "forecast_days": 2,
    })
    try:
        with urllib.request.urlopen(f"{OPEN_METEO_URL}?{params}", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    cache.set(METEO_CACHE_KEY, data, getattr(settings, "FARM_WEATHER_CACHE_SECONDS", 1800))
    return data


def fetch_openweathermap(timeout: int = 6) -> dict | None:
    """OWM 5-day/3-hour forecast. None when unconfigured or on failure."""
    if not getattr(settings, "OPENWEATHER_API_KEY", ""):
        return None
    cache = caches["default"]
    cached = cache.get(OWM_CACHE_KEY)
    if cached is not None:
        return cached
    params = urllib.parse.urlencode({
        "lat": settings.FARM_WEATHER_LAT,
        "lon": settings.FARM_WEATHER_LON,
        "appid": settings.OPENWEATHER_API_KEY,
        "units": "metric",
    })
    try:
        with urllib.request.urlopen(f"{OWM_FORECAST_URL}?{params}", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    cache.set(OWM_CACHE_KEY, data, getattr(settings, "FARM_WEATHER_CACHE_SECONDS", 1800))
    return data


def rain_next_24h_open_meteo(forecast: dict | None, now: datetime | None = None) -> float:
    """Sum hourly precipitation (mm) over the next 24h from now (UTC)."""
    if not forecast:
        return 0.0
    hourly = forecast.get("hourly") or {}
    times = hourly.get("time") or []
    amounts = hourly.get("precipitation") or []
    if not times or not amounts:
        return 0.0
    now = now or datetime.now(timezone.utc)
    end = now + timedelta(hours=24)
    total = 0.0
    for stamp, mm in zip(times, amounts):
        try:
            slot = datetime.strptime(stamp, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
            total += float(mm) if now <= slot < end else 0.0
        except (TypeError, ValueError):
            continue
    return total


def rain_next_24h_owm(forecast: dict | None) -> float:
    """Sum OWM 3-hour rain volumes (mm) over the next 24h (first 8 slots)."""
    if not forecast or not isinstance(forecast.get("list"), list):
        return 0.0
    total = 0.0
    for slot in forecast["list"][:8]:
        rain = slot.get("rain") or {}
        try:
            total += float(rain.get("3h", 0.0))
        except (TypeError, ValueError):
            continue
    return total


def rain_next_24h(forecast: dict | None) -> float:
    """Back-compat helper: sums OWM-style 3h slots (used by existing tests)."""
    return rain_next_24h_owm(forecast)


def weather_status() -> dict:
    """Small summary dict for the dashboard. Never raises."""
    threshold = float(getattr(settings, "FARM_RAIN_SKIP_MM", 5.0))
    city = getattr(settings, "FARM_WEATHER_CITY", "")
    if provider() == "openweathermap":
        if not getattr(settings, "OPENWEATHER_API_KEY", ""):
            return {"state": "unconfigured", "rain_mm": 0.0, "skip_watering": False}
        forecast = fetch_openweathermap()
        if forecast is None:
            return {"state": "unavailable", "rain_mm": 0.0, "skip_watering": False}
        rain_mm = rain_next_24h_owm(forecast)
    else:
        forecast = fetch_open_meteo()
        if forecast is None:
            return {"state": "unavailable", "rain_mm": 0.0, "skip_watering": False}
        rain_mm = rain_next_24h_open_meteo(forecast)
    return {
        "state": "ok",
        "rain_mm": round(rain_mm, 1),
        "threshold_mm": threshold,
        "skip_watering": rain_mm >= threshold,
        "city": city,
    }


def adjust_water_reminders(user) -> dict:
    """Postpone the user's due watering reminders by 1 day when rain is forecast.

    Returns {"adjusted": int, "rain_mm": float, "skipped": bool}.
    Only kind="water" reminders due today or overdue are touched; fertilize /
    harvest / custom reminders are left alone.
    """
    from .models import Reminder  # local import to avoid cycles

    status = weather_status()
    if not status["skip_watering"]:
        return {"adjusted": 0, "rain_mm": status["rain_mm"], "skipped": False}

    today = date.today()
    due = Reminder.objects.filter(
        user=user, kind="water", is_done=False, due_date__lte=today,
    )
    adjusted = 0
    for reminder in due:
        if reminder.due_date < today + timedelta(days=1):
            reminder.postponed_from = reminder.due_date
        reminder.due_date = today + timedelta(days=1)
        reminder.weather_paused = True
        reminder.save(update_fields=["due_date", "weather_paused", "postponed_from"])
        adjusted += 1
    return {"adjusted": adjusted, "rain_mm": status["rain_mm"], "skipped": True}
