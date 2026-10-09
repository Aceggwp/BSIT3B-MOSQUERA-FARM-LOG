from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import CareLog, DailyCheck, GardenArea, Plant, Reminder, defaults_for
from . import weather as farm_weather


# ---------- scoping helpers (same pattern as apps.scoping) ----------

def _plants(user):
    if user.is_superuser:
        return Plant.objects.all()
    return Plant.objects.filter(user=user)


def _plant(user, pk):
    return get_object_or_404(_plants(user), pk=pk)


def _areas(user):
    if user.is_superuser:
        return GardenArea.objects.all()
    return GardenArea.objects.filter(user=user)


def _area(user, pk):
    return get_object_or_404(_areas(user), pk=pk)


def _reminders(user):
    if user.is_superuser:
        return Reminder.objects.all()
    return Reminder.objects.filter(user=user)


def _carelog(user, pk):
    qs = CareLog.objects.all() if user.is_superuser else CareLog.objects.filter(user=user)
    return get_object_or_404(qs, pk=pk)


def _dailycheck(user, pk):
    qs = DailyCheck.objects.all() if user.is_superuser else DailyCheck.objects.filter(user=user)
    return get_object_or_404(qs, pk=pk)


# ---------- dashboard ----------

def _bulk_check(plants, today, **flags):
    """One-tap daily logging: get-or-create today's check per plant, set flags."""
    touched = 0
    for plant in plants:
        check, _ = DailyCheck.objects.get_or_create(
            plant=plant, date=today, defaults={"user": plant.user},
        )
        for key, value in flags.items():
            setattr(check, key, value)
        check.save()
        touched += 1
    return touched


def _clear_due_reminders(user, plants, kinds, as_of):
    _reminders(user).filter(
        plant__in=plants, kind__in=kinds, is_done=False, due_date__lte=as_of,
    ).update(is_done=True, done_at=as_of)


@login_required(login_url="login")
@require_POST
def quick_water_all(request):
    """One tap: mark every plant (or one plot's) watered today."""
    today = date.today()
    area_id = request.POST.get("area") or request.GET.get("area")
    plants = _plants(request.user)
    if area_id:
        plants = plants.filter(area_id=_area(request.user, area_id).id)
    plants = list(plants)
    touched = _bulk_check(plants, today, watered=True)
    _clear_due_reminders(request.user, plants, ["water"], today)
    messages.success(request, f"Watered {touched} plant(s) logged for today.")
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"status": "success", "touched": touched})
    return redirect("farm:dashboard")


@login_required(login_url="login")
@require_POST
def quick_fertilize_all(request):
    """One tap: mark every plant (or one plot's) fertilized today."""
    today = date.today()
    area_id = request.POST.get("area") or request.GET.get("area")
    plants = _plants(request.user)
    if area_id:
        plants = plants.filter(area_id=_area(request.user, area_id).id)
    plants = list(plants)
    touched = _bulk_check(plants, today, fertilized=True)
    _clear_due_reminders(request.user, plants, ["fertilize"], today)
    messages.success(request, f"Fertilized {touched} plant(s) logged for today.")
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"status": "success", "touched": touched})
    return redirect("farm:dashboard")


@login_required(login_url="login")
@require_POST
def quick_pest(request):
    """One tap: log 'Pest spotted' on one plant's care history."""
    plant = _plant(request.user, request.POST.get("plant"))
    note = request.POST.get("note", "").strip() or "Pest spotted (quick log)."
    log = CareLog.objects.create(
        user=request.user, plant=plant, date=date.today(),
        category="pest", description=note,
    )
    messages.warning(request, f"Pest logged on {plant.name}. Check it soon.")
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"status": "success", "id": log.id})
    return redirect("farm:plant_detail", pk=plant.id)

@login_required(login_url="login")
def dashboard(request):
    today = date.today()
    plants = _plants(request.user)
    due = _reminders(request.user).filter(is_done=False, due_date__lte=today).order_by("due_date")[:10]
    upcoming = _reminders(request.user).filter(is_done=False, due_date__gt=today).order_by("due_date")[:10]
    ready = [p for p in plants if p.is_ready][:10]
    checks_qs = DailyCheck.objects.all() if request.user.is_superuser else DailyCheck.objects.filter(user=request.user)
    recent_checks = checks_qs.order_by("-date")[:8]
    context = {
        "plant_count": plants.count(),
        "due_count": _reminders(request.user).filter(is_done=False, due_date__lte=today).count(),
        "today": today,
        "weather": farm_weather.weather_status(),
        "due": due,
        "upcoming": upcoming,
        "ready": ready,
        "recent_checks": recent_checks,
        "plants": plants.order_by("name")[:10],
        "areas": _areas(request.user).order_by("name"),
        "all_plants": plants.order_by("name"),
    }
    return render(request, "farm/dashboard.html", context)


@login_required(login_url="login")
def stats_ajax(request):
    """Live counters for the dashboard cards + sidebar badges. No page reload."""
    today = date.today()
    plants = _plants(request.user)
    return JsonResponse({
        "plant_count": plants.count(),
        "due_count": _reminders(request.user).filter(is_done=False, due_date__lte=today).count(),
        "ready_count": sum(1 for p in plants if p.is_ready),
    })


# ---------- plants ----------

@login_required(login_url="login")
def plant_list_page(request):
    import json
    query = request.GET.get("q", "").strip()
    qs = _plants(request.user).order_by("name")
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(variety__icontains=query))
    paginator = Paginator(qs, 10)
    plants = paginator.get_page(request.GET.get("page", 1))
    areas = list(_areas(request.user).prefetch_related("plants"))
    area_map = {}
    for area in areas:
        area_map[str(area.id)] = {
            "rows": area.rows, "cols": area.cols,
            "cells": [[p.pos_x, p.pos_y, p.name] for p in area.plants.all()
                      if 0 <= p.pos_x < area.cols and 0 <= p.pos_y < area.rows],
        }
    return render(request, "farm/plants.html", {
        "plants": plants, "query": query, "areas": areas,
        "area_map_json": json.dumps(area_map),
    })


@login_required(login_url="login")
def plant_detail_page(request, pk):
    plant = _plant(request.user, pk)
    reminders = plant.reminders.order_by("due_date")
    logs = plant.care_logs.order_by("-date")[:50]
    checks = plant.daily_checks.order_by("-date")[:30]
    return render(request, "farm/plant_detail.html", {
        "plant": plant,
        "reminders": reminders,
        "logs": logs,
        "checks": checks,
    })


def _parse_plant_form(request, plant):
    name = request.POST.get("name", "").strip()
    variety = request.POST.get("variety", "").strip()
    planting_date = request.POST.get("planting_date", "").strip()
    area_id = request.POST.get("area", "").strip()
    if not name:
        return None, "Plant name is required."
    plant.name = name
    plant.variety = variety
    try:
        if planting_date:
            plant.planting_date = date.fromisoformat(planting_date)
    except ValueError:
        return None, "Invalid planting date."
    # Auto-fill tailored defaults when user leaves them blank.
    d = defaults_for(name)
    try:
        plant.days_to_harvest = int(request.POST.get("days_to_harvest") or d["days_to_harvest"])
        plant.water_every_days = int(request.POST.get("water_every_days") or d["water_every_days"])
        plant.fertilize_every_days = int(request.POST.get("fertilize_every_days") or d["fertilize_every_days"])
        plant.quantity = int(request.POST.get("quantity") or 1)
        plant.pos_x = int(request.POST.get("pos_x") or 0)
        plant.pos_y = int(request.POST.get("pos_y") or 0)
    except (TypeError, ValueError):
        return None, "Numeric fields must be valid numbers."
    if plant.days_to_harvest < 1 or plant.water_every_days < 1 or plant.fertilize_every_days < 1:
        return None, "Intervals must be at least 1."
    status = request.POST.get("status", "").strip()
    if status:
        plant.status = status
    if area_id:
        plant.area = _area(request.user, area_id)
    else:
        plant.area = None
    plant.notes = request.POST.get("notes", "").strip()
    return plant, None


@login_required(login_url="login")
def plant_get_ajax(request, pk):
    plant = _plant(request.user, pk)
    return JsonResponse({
        "id": plant.id, "name": plant.name, "variety": plant.variety,
        "planting_date": plant.planting_date.isoformat(),
        "days_to_harvest": plant.days_to_harvest,
        "water_every_days": plant.water_every_days,
        "fertilize_every_days": plant.fertilize_every_days,
        "quantity": plant.quantity, "status": plant.status,
        "area": plant.area_id, "pos_x": plant.pos_x, "pos_y": plant.pos_y,
        "notes": plant.notes,
        "expected_harvest_date": plant.expected_harvest_date.isoformat(),
    })


@login_required(login_url="login")
@require_POST
def plant_save_ajax(request):
    pk = request.POST.get("id")
    if pk:
        plant = _plant(request.user, pk)
        is_update = True
    else:
        plant = Plant(user=request.user)
        is_update = False
    plant, error = _parse_plant_form(request, plant)
    if error:
        return JsonResponse({"error": error}, status=400)
    if not plant.pk:
        plant.apply_vegetable_defaults()
        plant.user = request.user
    plant.save()
    # Auto-generate tailored reminders on creation.
    if not is_update and not plant.reminders.exists():
        Reminder.objects.bulk_create(Reminder.build_defaults_for_plant(plant))
    messages.success(request, f'Plant "{plant.name}" {"updated" if is_update else "saved"}.')
    return JsonResponse({"status": "success", "id": plant.id, "name": plant.name})


@login_required(login_url="login")
@require_POST
def plant_delete_ajax(request, pk):
    plant = _plant(request.user, pk)
    name = plant.name
    plant.delete()
    messages.success(request, f'Plant "{name}" deleted.')
    return JsonResponse({"status": "deleted"})


@login_required(login_url="login")
@require_POST
def plant_generate_reminders(request, pk):
    plant = _plant(request.user, pk)
    pending_kinds = set(plant.reminders.filter(is_done=False).values_list("kind", flat=True))
    fresh = [r for r in Reminder.build_defaults_for_plant(plant) if r.kind not in pending_kinds]
    created = Reminder.objects.bulk_create(fresh)
    if created:
        messages.success(request, f"{len(created)} reminders generated for {plant.name}.")
    else:
        messages.info(request, f"{plant.name} already has pending reminders — nothing duplicated.")
    return JsonResponse({"status": "success", "count": len(created)})


# ---------- garden areas + map ----------

@login_required(login_url="login")
def area_list_page(request):
    areas = _areas(request.user).order_by("name")
    return render(request, "farm/areas.html", {"areas": areas})


@login_required(login_url="login")
@require_POST
def area_save_ajax(request):
    pk = request.POST.get("id")
    if pk:
        area = _area(request.user, pk)
    else:
        area = GardenArea(user=request.user)
    area.name = request.POST.get("name", "").strip()
    if not area.name:
        return JsonResponse({"error": "Area name is required."}, status=400)
    area.kind = request.POST.get("kind", "raised_bed")
    try:
        area.rows = max(1, int(request.POST.get("rows") or 4))
        area.cols = max(1, int(request.POST.get("cols") or 4))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Rows/cols must be numbers."}, status=400)
    area.description = request.POST.get("description", "").strip()
    try:
        area.save()
    except IntegrityError:
        return JsonResponse({"error": "You already have an area with that name."}, status=400)
    return JsonResponse({"status": "success", "id": area.id, "name": area.name})


@login_required(login_url="login")
@require_POST
def area_delete_ajax(request, pk):
    area = _area(request.user, pk)
    area.delete()
    return JsonResponse({"status": "deleted"})


@login_required(login_url="login")
@require_POST
def map_auto_arrange(request):
    """Automation: place unplaced (or off-grid) plants into empty cells.

    Optional POST `area` limits the run to one plot. Cells that would create
    a bad companion pairing are avoided when alternatives exist.
    """
    from .companion import find_spot
    area_id = request.POST.get("area")
    if area_id:
        areas = [_area(request.user, area_id)]
        unplaced = _plants(request.user).filter(area__isnull=True)
    else:
        areas = list(_areas(request.user))
        unplaced = _plants(request.user).filter(area__isnull=True)
    unplaced = list(unplaced.order_by("name"))
    placed, skipped = 0, 0
    for area in areas:
        occupants = [p for p in area.plants.all()]
        for plant in [p for p in unplaced]:
            spot = find_spot(area, occupants, plant.name)
            if spot is None:
                continue
            plant.area = area
            plant.pos_x, plant.pos_y = spot
            plant.save(update_fields=["area", "pos_x", "pos_y"])
            occupants.append(plant)
            unplaced.remove(plant)
            placed += 1
    skipped = len(unplaced)
    if placed:
        messages.success(request, f"Auto-arranged {placed} plant(s).")
    if skipped:
        messages.warning(request, f"{skipped} plant(s) left: no empty cells.")
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"status": "success", "placed": placed, "skipped": skipped})
    return redirect("farm:map")


@login_required(login_url="login")
@require_POST
def plant_move_ajax(request, pk):
    """Free-move a plant to another cell (same or different plot)."""
    plant = _plant(request.user, pk)
    area_id = request.POST.get("area")
    if not area_id:
        return JsonResponse({"error": "Plot is required."}, status=400)
    area = _area(request.user, area_id)
    try:
        x, y = int(request.POST.get("pos_x")), int(request.POST.get("pos_y"))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Cell coordinates must be numbers."}, status=400)
    if not (0 <= x < area.cols and 0 <= y < area.rows):
        return JsonResponse({"error": f"Cell ({x},{y}) is outside {area.name}."}, status=400)
    plant.area = area
    plant.pos_x, plant.pos_y = x, y
    plant.save(update_fields=["area", "pos_x", "pos_y"])
    return JsonResponse({"status": "moved", "area": area.id, "pos_x": x, "pos_y": y})


@login_required(login_url="login")
def map_view(request):
    from .companion import analyze
    areas = list(_areas(request.user).prefetch_related("plants"))
    grids = []
    for area in areas:
        # rows x cols matrix; each cell holds the plants at (pos_x, pos_y).
        grid = [[[] for _ in range(area.cols)] for _ in range(area.rows)]
        overflow = []
        area_plants = list(area.plants.all())
        for plant in area_plants:
            if 0 <= plant.pos_x < area.cols and 0 <= plant.pos_y < area.rows:
                grid[plant.pos_y][plant.pos_x].append(plant)
            else:
                overflow.append(plant)
        alerts = analyze(area_plants)
        bad_ids, good_ids = set(), set()
        for alert in alerts:
            (bad_ids if alert["kind"] == "bad" else good_ids).update(alert["ids"])
        grids.append({"area": area, "grid": grid, "overflow": overflow,
                      "alerts": alerts, "bad_ids": bad_ids, "good_ids": good_ids})
    unplaced = _plants(request.user).filter(area__isnull=True)
    return render(request, "farm/map.html", {"grids": grids, "unplaced": unplaced})


# ---------- reminders ----------

@login_required(login_url="login")
def reminder_list_page(request):
    show = request.GET.get("show", "due")
    qs = _reminders(request.user).select_related("plant")
    today = date.today()
    if show == "done":
        qs = qs.filter(is_done=True).order_by("-done_at")
    elif show == "all":
        qs = qs.order_by("is_done", "due_date")
    else:  # due
        qs = qs.filter(is_done=False).order_by("due_date")
    paginator = Paginator(qs, 15)
    reminders = paginator.get_page(request.GET.get("page", 1))
    plants = _plants(request.user).order_by("name")
    return render(request, "farm/reminders.html", {
        "reminders": reminders, "show": show, "plants": plants, "today": today,
    })


@login_required(login_url="login")
@require_POST
def reminder_save_ajax(request):
    pk = request.POST.get("id")
    if pk:
        reminder = get_object_or_404(_reminders(request.user), pk=pk)
    else:
        reminder = Reminder(user=request.user)
    plant_id = request.POST.get("plant")
    if not plant_id:
        return JsonResponse({"error": "Plant is required."}, status=400)
    reminder.plant = _plant(request.user, plant_id)
    reminder.kind = request.POST.get("kind", "custom")
    reminder.message = request.POST.get("message", "").strip()
    if not reminder.message:
        # Tailored default message per kind.
        defaults = {
            "water": f"Water the {reminder.plant.name.lower()} today",
            "fertilize": f"Fertilize the {reminder.plant.name.lower()} this weekend",
            "harvest": f"Check the {reminder.plant.name.lower()} for harvest",
        }
        reminder.message = defaults.get(reminder.kind, f"Check the {reminder.plant.name.lower()}")
    try:
        reminder.due_date = date.fromisoformat(request.POST.get("due_date"))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Invalid due date."}, status=400)
    if not reminder.pk:
        reminder.user = request.user
    reminder.save()
    return JsonResponse({"status": "success", "id": reminder.id})


@login_required(login_url="login")
@require_POST
def reminder_toggle_ajax(request, pk):
    reminder = get_object_or_404(_reminders(request.user), pk=pk)
    reminder.is_done = not reminder.is_done
    reminder.done_at = date.today() if reminder.is_done else None
    reminder.save()
    return JsonResponse({"status": "success", "is_done": reminder.is_done})


@login_required(login_url="login")
@require_POST
def reminder_delete_ajax(request, pk):
    reminder = get_object_or_404(_reminders(request.user), pk=pk)
    reminder.delete()
    return JsonResponse({"status": "deleted"})


@login_required(login_url="login")
@require_POST
def weather_adjust(request):
    """Check the rain forecast and postpone due watering reminders if needed."""
    result = farm_weather.adjust_water_reminders(request.user)
    if result["skipped"]:
        messages.warning(
            request,
            f'Heavy rain forecast ({result["rain_mm"]} mm in 24h). '
            f'{result["adjusted"]} watering reminder(s) paused until tomorrow.',
        )
    else:
        messages.info(request, f'No heavy rain forecast ({result["rain_mm"]} mm). Water as normal.')
    return redirect("farm:dashboard")


@login_required(login_url="login")
@require_POST
def ai_advice_ajax(request, pk):
    """Ask the configured AI backend about plant pk; save the answer to care history."""
    from django.conf import settings as dj_settings

    from . import ai_advice as gemini
    from . import ai_openrouter as orouter

    plant = _plant(request.user, pk)
    use_openrouter = getattr(dj_settings, "AI_PROVIDER", "gemini") == "openrouter"
    if use_openrouter:
        if not orouter.is_configured():
            return JsonResponse(
                {"error": "Set OPENROUTER_API_KEY to enable AI advice. Get a key at https://openrouter.ai/keys."},
                status=400,
            )
        backend_name, ask = f"OpenRouter ({orouter.model_name()})", orouter.ask_openrouter
    else:
        if not gemini.is_configured():
            return JsonResponse(
                {"error": "Set GEMINI_API_KEY to enable AI advice. Get a free key at https://aistudio.google.com."},
                status=400,
            )
        backend_name, ask = f"Gemini ({gemini.model_name()})", None
    logs = list(plant.care_logs.order_by("-date")[:5])
    checks = list(plant.daily_checks.order_by("-date")[:5])
    if use_openrouter:
        result = ask(gemini.build_prompt(plant, logs, checks, farm_weather.weather_status()))
    else:
        result = gemini.plant_advice(plant, logs, checks, farm_weather.weather_status())
    if not result["ok"]:
        return JsonResponse({"error": result["error"]}, status=502)
    log = CareLog.objects.create(
        user=request.user, plant=plant, date=date.today(),
        category="note", description=f"AI advice [{backend_name}]: {result['text']}",
    )
    return JsonResponse({"status": "success", "id": log.id, "advice": result["text"]})


# ---------- care history ----------

@login_required(login_url="login")
def carelog_list_page(request):
    """All care-history entries across the user's plants, newest first."""
    logs = CareLog.objects.select_related("plant").order_by("-date", "-created_at")
    if not request.user.is_superuser:
        logs = logs.filter(user=request.user)
    plant_id = request.GET.get("plant", "").strip()
    category = request.GET.get("category", "").strip()
    if plant_id:
        logs = logs.filter(plant_id=int(plant_id)) if plant_id.isdigit() else logs.none()
    if category:
        logs = logs.filter(category=category)
    paginator = Paginator(logs, 15)
    page = paginator.get_page(request.GET.get("page", 1))
    plants = _plants(request.user).order_by("name")
    return render(request, "farm/carelogs.html", {
        "logs": page, "plants": plants,
        "plant_id": plant_id, "category": category,
        "categories": CareLog.CATEGORY_CHOICES,
    })

@login_required(login_url="login")
@require_POST
def carelog_save_ajax(request, pk):
    """Create a care-history entry for plant pk."""
    plant = _plant(request.user, pk)
    description = request.POST.get("description", "").strip()
    if not description:
        return JsonResponse({"error": "Description is required."}, status=400)
    try:
        log_date = date.fromisoformat(request.POST.get("date")) if request.POST.get("date") else date.today()
    except ValueError:
        return JsonResponse({"error": "Invalid date."}, status=400)
    photo = request.FILES.get("photo")
    if photo:
        if photo.size > 5 * 1024 * 1024:
            return JsonResponse({"error": "Photo must be under 5 MB."}, status=400)
        if photo.content_type not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
            return JsonResponse({"error": "Photo must be JPG, PNG, WEBP, or GIF."}, status=400)
    log = CareLog.objects.create(
        user=request.user, plant=plant, date=log_date,
        category=request.POST.get("category", "note"), description=description,
        photo=photo,
    )
    return JsonResponse({"status": "success", "id": log.id,
                         "photo_url": log.photo.url if log.photo else ""})


@login_required(login_url="login")
@require_POST
def carelog_delete_ajax(request, pk):
    log = _carelog(request.user, pk)
    log.delete()
    return JsonResponse({"status": "deleted"})


# ---------- daily monitoring ----------

@login_required(login_url="login")
@require_POST
def dailycheck_save_ajax(request, pk):
    """Create or update the daily monitoring entry for plant pk + date."""
    plant = _plant(request.user, pk)
    try:
        check_date = date.fromisoformat(request.POST.get("date")) if request.POST.get("date") else date.today()
    except ValueError:
        return JsonResponse({"error": "Invalid date."}, status=400)
    height = request.POST.get("height_cm") or None
    try:
        height_val = float(height) if height else None
    except ValueError:
        return JsonResponse({"error": "Height must be a number."}, status=400)
    check, _ = DailyCheck.objects.get_or_create(
        plant=plant, date=check_date, defaults={"user": request.user},
    )
    check.watered = request.POST.get("watered") in ("true", "on", "1")
    check.fertilized = request.POST.get("fertilized") in ("true", "on", "1")
    check.health = request.POST.get("health", "good")
    check.height_cm = height_val
    check.notes = request.POST.get("notes", "").strip()
    check.save()
    # Mark matching water/fertilize reminders due today as done automatically.
    if check.watered or check.fertilized:
        kinds = []
        if check.watered:
            kinds.append("water")
        if check.fertilized:
            kinds.append("fertilize")
        _reminders(request.user).filter(
            plant=plant, kind__in=kinds, is_done=False, due_date__lte=check_date,
        ).update(is_done=True, done_at=check_date)
    return JsonResponse({"status": "success", "id": check.id})


@login_required(login_url="login")
@require_POST
def dailycheck_delete_ajax(request, pk):
    check = _dailycheck(request.user, pk)
    check.delete()
    return JsonResponse({"status": "deleted"})
