from django.contrib import admin

from .models import CareLog, DailyCheck, GardenArea, Plant, Reminder


@admin.register(GardenArea)
class GardenAreaAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "user", "rows", "cols")
    list_filter = ("kind",)


@admin.register(Plant)
class PlantAdmin(admin.ModelAdmin):
    list_display = ("name", "variety", "user", "area", "planting_date", "status")
    list_filter = ("status",)


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ("plant", "kind", "due_date", "is_done", "user")
    list_filter = ("kind", "is_done")


@admin.register(CareLog)
class CareLogAdmin(admin.ModelAdmin):
    list_display = ("plant", "category", "date", "user")
    list_filter = ("category",)


@admin.register(DailyCheck)
class DailyCheckAdmin(admin.ModelAdmin):
    list_display = ("plant", "date", "health", "watered", "fertilized")
    list_filter = ("health",)
