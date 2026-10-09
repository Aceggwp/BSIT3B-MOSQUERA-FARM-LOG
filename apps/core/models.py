from django.conf import settings
from django.db import models


class LoginEvent(models.Model):
    """One recorded sign-in (who, when, from where)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="login_events",
        on_delete=models.CASCADE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} signed in {self.created_at:%Y-%m-%d %H:%M}"
