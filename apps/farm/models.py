"""Models for Mosquera Farm Log.

Covers: planting & harvest tracking, custom reminders,
garden layout map, care history, daily monitoring.
"""

from datetime import date, timedelta

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


# Sensible defaults per vegetable so reminders feel "tailored"
# (e.g. "Water the lettuce today" vs "Fertilize the tomatoes").
VEGETABLE_DEFAULTS = {
    "lettuce": {"days_to_harvest": 45, "water_every_days": 1, "fertilize_every_days": 14},
    "tomato": {"days_to_harvest": 70, "water_every_days": 2, "fertilize_every_days": 14},
    "tomatoes": {"days_to_harvest": 70, "water_every_days": 2, "fertilize_every_days": 14},
    "carrot": {"days_to_harvest": 70, "water_every_days": 2, "fertilize_every_days": 21},
    "cabbage": {"days_to_harvest": 80, "water_every_days": 2, "fertilize_every_days": 14},
    "eggplant": {"days_to_harvest": 75, "water_every_days": 2, "fertilize_every_days": 14},
    "pepper": {"days_to_harvest": 70, "water_every_days": 2, "fertilize_every_days": 14},
    "cucumber": {"days_to_harvest": 55, "water_every_days": 1, "fertilize_every_days": 14},
    "okra": {"days_to_harvest": 60, "water_every_days": 2, "fertilize_every_days": 21},
    "beans": {"days_to_harvest": 55, "water_every_days": 2, "fertilize_every_days": 21},
    "default": {"days_to_harvest": 60, "water_every_days": 2, "fertilize_every_days": 14},
}


def defaults_for(name: str) -> dict:
    key = (name or "").strip().lower()
    return VEGETABLE_DEFAULTS.get(key, VEGETABLE_DEFAULTS["default"])


class GardenArea(models.Model):
    """A named growing space used by the Garden Layout Map."""

    KIND_CHOICES = [
        ("yard", "Yard"),
        ("raised_bed", "Raised Bed"),
        ("indoor_pot", "Indoor Pot"),
        ("greenhouse", "Greenhouse"),
        ("other", "Other"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="garden_areas",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default="raised_bed")
    rows = models.PositiveIntegerField(default=4, validators=[MinValueValidator(1)])
    cols = models.PositiveIntegerField(default=4, validators=[MinValueValidator(1)])
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["user", "name"], name="unique_area_per_user"),
        ]

    def __str__(self):
        return self.name


class Plant(models.Model):
    """A planting: what was planted, where, when, and when it is ready."""

    STATUS_CHOICES = [
        ("seed", "Seed"),
        ("seedling", "Seedling"),
        ("growing", "Growing"),
        ("flowering", "Flowering"),
        ("ready", "Ready to harvest"),
        ("harvested", "Harvested"),
        ("dead", "Dead"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="plants", on_delete=models.CASCADE
    )
    area = models.ForeignKey(
        GardenArea, related_name="plants",
        on_delete=models.SET_NULL, null=True, blank=True,
    )
    name = models.CharField(max_length=120, help_text="Vegetable name, e.g. Lettuce")
    variety = models.CharField(max_length=120, blank=True)
    planting_date = models.DateField(default=date.today)
    days_to_harvest = models.PositiveIntegerField(default=60, validators=[MinValueValidator(1)])
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="seedling")
    water_every_days = models.PositiveIntegerField(default=2, validators=[MinValueValidator(1)])
    fertilize_every_days = models.PositiveIntegerField(default=14, validators=[MinValueValidator(1)])
    # Position inside the area grid for the visual map.
    pos_x = models.PositiveIntegerField(default=0)
    pos_y = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.planting_date})"

    @property
    def expected_harvest_date(self):
        return self.planting_date + timedelta(days=self.days_to_harvest)

    @property
    def days_until_harvest(self):
        return (self.expected_harvest_date - date.today()).days

    @property
    def is_ready(self):
        return self.days_until_harvest <= 0 and self.status not in ("harvested", "dead")

    def apply_vegetable_defaults(self):
        d = defaults_for(self.name)
        if not self.pk:
            # Only fill unset/primitive defaults on creation.
            if self.days_to_harvest == 60:
                self.days_to_harvest = d["days_to_harvest"]
            if self.water_every_days == 2:
                self.water_every_days = d["water_every_days"]
            if self.fertilize_every_days == 14:
                self.fertilize_every_days = d["fertilize_every_days"]


class Reminder(models.Model):
    """Custom automated alert for a plant (water / fertilize / harvest / custom)."""

    KIND_CHOICES = [
        ("water", "Water"),
        ("fertilize", "Fertilize"),
        ("harvest", "Harvest"),
        ("custom", "Custom"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="reminders", on_delete=models.CASCADE
    )
    plant = models.ForeignKey(Plant, related_name="reminders", on_delete=models.CASCADE)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default="custom")
    message = models.CharField(max_length=255)
    due_date = models.DateField(default=date.today)
    is_done = models.BooleanField(default=False)
    done_at = models.DateField(null=True, blank=True)
    # Weather-adaptive reminders: set when a watering alert was auto-paused
    # because heavy rain was forecast.
    weather_paused = models.BooleanField(default=False)
    postponed_from = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "-created_at"]

    def __str__(self):
        return f"{self.plant.name}: {self.message}"

    @property
    def is_overdue(self):
        return not self.is_done and self.due_date < date.today()

    @property
    def is_due_today(self):
        return not self.is_done and self.due_date == date.today()

    @property
    def days_overdue(self):
        if self.is_done or self.due_date >= date.today():
            return 0
        return (date.today() - self.due_date).days

    @property
    def days_until_due(self):
        if self.is_done:
            return 0
        return max(0, (self.due_date - date.today()).days)

    @classmethod
    def build_defaults_for_plant(cls, plant: Plant, user=None):
        """Generate tailored water / fertilize / harvest reminders for a plant."""
        today = date.today()
        owner = user or plant.user
        reminders = [
            cls(
                user=owner, plant=plant, kind="water",
                message=f"Water the {plant.name.lower()} today",
                due_date=today + timedelta(days=plant.water_every_days),
            ),
            cls(
                user=owner, plant=plant, kind="fertilize",
                message=f"Fertilize the {plant.name.lower()} this weekend",
                due_date=today + timedelta(days=plant.fertilize_every_days),
            ),
            cls(
                user=owner, plant=plant, kind="harvest",
                message=f"Harvest the {plant.name.lower()} around {plant.expected_harvest_date}",
                due_date=plant.expected_harvest_date,
            ),
        ]
        return reminders


class CareLog(models.Model):
    """Digital care-history log: growth, pest, weather, or general note."""

    CATEGORY_CHOICES = [
        ("growth", "Growth progress"),
        ("pest", "Pest issue"),
        ("weather", "Weather change"),
        ("note", "Note"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="care_logs", on_delete=models.CASCADE
    )
    plant = models.ForeignKey(Plant, related_name="care_logs", on_delete=models.CASCADE)
    date = models.DateField(default=date.today)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="note")
    description = models.TextField()
    photo = models.ImageField(upload_to="care_photos/%Y/%m/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.plant.name} [{self.category}] {self.date}"


class DailyCheck(models.Model):
    """Daily monitoring entry for one plant on one day."""

    HEALTH_CHOICES = [
        ("poor", "Poor"),
        ("fair", "Fair"),
        ("good", "Good"),
        ("excellent", "Excellent"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="daily_checks", on_delete=models.CASCADE
    )
    plant = models.ForeignKey(Plant, related_name="daily_checks", on_delete=models.CASCADE)
    date = models.DateField(default=date.today)
    watered = models.BooleanField(default=False)
    fertilized = models.BooleanField(default=False)
    health = models.CharField(max_length=20, choices=HEALTH_CHOICES, default="good")
    height_cm = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(fields=["plant", "date"], name="unique_check_per_plant_day"),
        ]

    def __str__(self):
        return f"{self.plant.name} check {self.date}"
