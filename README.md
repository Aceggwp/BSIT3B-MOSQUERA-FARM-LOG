# ProjectV3 — Mosquera Farm Log

Django farm management app: planting & harvest tracking, custom reminders
(weather-adaptive via Open-Meteo), visual garden layout map with companion
planting alerts, care history with progress photos, daily monitoring with
quick-log shortcuts, AI advice (Gemini / OpenRouter), role-based auth
(admin + staff), and login tracking.

## Members

- Mosquera, Carl John
- Lirazan, Adrian
- Lucasan, Arc Xerlan — BSIT 3-B

## Run locally

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Optional integrations via environment variables (no keys needed for the
default weather provider):

```bash
set FARM_WEATHER_LAT=14.5995
set FARM_WEATHER_LON=120.9842
set GEMINI_API_KEY=your_key
set AI_PROVIDER=gemini
set OPENROUTER_API_KEY=your_key   # with AI_PROVIDER=openrouter
```
