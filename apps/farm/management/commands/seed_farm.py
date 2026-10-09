"""Seed example Mosquera Farm Log data so you can study every feature.

Usage:
    python manage.py seed_farm --username admin
    python manage.py seed_farm --username admin --clear   # wipe user's farm data first
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.farm.models import CareLog, DailyCheck, GardenArea, Plant, Reminder


class Command(BaseCommand):
    help = "Create example farm data (areas, plants, reminders, logs, checks)."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="admin")
        parser.add_argument("--clear", action="store_true")

    def handle(self, *args, **options):
        User = get_user_model()
        user = User.objects.filter(username=options["username"]).first()
        if not user:
            self.stderr.write(f'User "{options["username"]}" not found.')
            return

        if options["clear"]:
            Plant.objects.filter(user=user).delete()
            GardenArea.objects.filter(user=user).delete()
            Reminder.objects.filter(user=user).delete()
            CareLog.objects.filter(user=user).delete()
            DailyCheck.objects.filter(user=user).delete()

        today = date.today()

        bed_a = GardenArea.objects.create(
            user=user, name="Raised Bed A", kind="raised_bed", rows=4, cols=4,
            description="Leafy greens near the kitchen door.",
        )
        backyard = GardenArea.objects.create(
            user=user, name="Backyard North", kind="yard", rows=3, cols=5,
            description="Full-sun row for fruiting vegetables.",
        )
        shelf = GardenArea.objects.create(
            user=user, name="Indoor Shelf", kind="indoor_pot", rows=2, cols=4,
            description="Seedlings under grow lights.",
        )

        specs = [
            # name, variety, planted_days_ago, status, area, x, y
            ("Lettuce", "Romaine", 30, "growing", bed_a, 0, 0),
            ("Tomato", "Cherry", 65, "ready", backyard, 0, 1),
            ("Cucumber", "Suyo", 5, "seedling", bed_a, 1, 0),
            ("Pepper", "Bell", 20, "growing", shelf, 0, 2),
            ("Carrots", "Nantes", 10, "growing", None, 0, 0),  # unplaced: shows on map page
        ]
        plants = []
        for name, variety, ago, status, area, x, y in specs:
            plant = Plant(user=user, name=name, variety=variety,
                          planting_date=today - timedelta(days=ago),
                          status=status, area=area, pos_x=x, pos_y=y, quantity=4)
            plant.apply_vegetable_defaults()
            plant.save()
            plants.append(plant)
            Reminder.objects.bulk_create(Reminder.build_defaults_for_plant(plant, user))

        lettuce, tomato = plants[0], plants[1]

        # An overdue reminder + a done one, so the dashboard states are visible.
        Reminder.objects.create(user=user, plant=lettuce, kind="water",
                                message="Water the lettuce today (missed yesterday)",
                                due_date=today - timedelta(days=1))
        Reminder.objects.create(user=user, plant=tomato, kind="fertilize",
                                message="Fertilize the tomatoes this weekend",
                                due_date=today, is_done=True, done_at=today)

        # Care history: one of each category.
        CareLog.objects.create(user=user, plant=lettuce, date=today - timedelta(days=6),
                               category="growth", description="First true leaves out, ~5cm tall.")
        CareLog.objects.create(user=user, plant=tomato, date=today - timedelta(days=3),
                               category="pest", description="Aphids on lower leaves; sprayed neem oil.")
        CareLog.objects.create(user=user, plant=tomato, date=today - timedelta(days=1),
                               category="weather", description="Heavy rain overnight; checked drainage.")
        CareLog.objects.create(user=user, plant=plants[2], date=today,
                               category="note", description="Thinned seedlings to 2 per cell.")

        # Daily monitoring: yesterday + today.
        DailyCheck.objects.create(user=user, plant=lettuce, date=today - timedelta(days=1),
                                  watered=True, health="good", height_cm=5.5,
                                  notes="Soil moist, no wilting.")
        DailyCheck.objects.create(user=user, plant=lettuce, date=today,
                                  watered=True, fertilized=False, health="excellent",
                                  height_cm=6.0, notes="Perky after morning watering.")
        DailyCheck.objects.create(user=user, plant=tomato, date=today,
                                  watered=True, health="fair",
                                  notes="Lower leaves yellowing, watching it.")

        self.stdout.write(
            f"Seeded {GardenArea.objects.filter(user=user).count()} areas, "
            f"{Plant.objects.filter(user=user).count()} plants, "
            f"{Reminder.objects.filter(user=user).count()} reminders, "
            f"{CareLog.objects.filter(user=user).count()} care logs, "
            f"{DailyCheck.objects.filter(user=user).count()} daily checks "
            f'for "{user.username}".'
        )
