"""Sidebar badge counts for the Mosquera Farm Log nav."""

from datetime import date


def farm_nav(request):
    from apps.farm.views import _plants, _reminders

    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}

    today = date.today()
    counts = {
        "nav_plant_count": _plants(user).count(),
        "nav_due_count": _reminders(user).filter(is_done=False, due_date__lte=today).count(),
    }
    return counts
