from django.contrib import admin

from .models import LoginEvent


@admin.register(LoginEvent)
class LoginEventAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "ip_address")
    list_filter = ("created_at",)
    date_hierarchy = "created_at"
