from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.farm.models import CareLog, DailyCheck, GardenArea, Plant, Reminder, defaults_for


class FarmModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="farmer", password="secret1234")

    def test_harvest_date_calculation(self):
        plant = Plant.objects.create(
            user=self.user, name="Lettuce",
            planting_date=date.today() - timedelta(days=10),
            days_to_harvest=45,
        )
        self.assertEqual(plant.expected_harvest_date, date.today() + timedelta(days=35))
        self.assertEqual(plant.days_until_harvest, 35)

    def test_vegetable_defaults_tailored(self):
        self.assertEqual(defaults_for("lettuce")["water_every_days"], 1)
        self.assertEqual(defaults_for("tomato")["days_to_harvest"], 70)

    def test_reminder_defaults_generation(self):
        plant = Plant.objects.create(user=self.user, name="Tomato", planting_date=date.today())
        plant.apply_vegetable_defaults()
        plant.save()
        rems = Reminder.build_defaults_for_plant(plant)
        kinds = {r.kind for r in rems}
        self.assertEqual(kinds, {"water", "fertilize", "harvest"})
        Reminder.objects.bulk_create(rems)
        self.assertEqual(plant.reminders.count(), 3)
        self.assertIn("tomato", plant.reminders.first().message.lower())

    def test_daily_check_unique_per_day(self):
        plant = Plant.objects.create(user=self.user, name="Okra")
        DailyCheck.objects.create(user=self.user, plant=plant, date=date.today())
        with self.assertRaises(Exception):
            DailyCheck.objects.create(user=self.user, plant=plant, date=date.today())

    def test_scoping_other_user_cannot_access(self):
        other = get_user_model().objects.create_user(username="other", password="x" * 10)
        plant = Plant.objects.create(user=self.user, name="Beans")
        self.client.force_login(other)
        response = self.client.get(reverse("farm:plant_detail", args=[plant.id]))
        self.assertEqual(response.status_code, 404)


class FarmViewTests(TestCase):
    def setUp(self):
        import tempfile
        from django.test import override_settings
        self._media = tempfile.mkdtemp()
        self._media_override = override_settings(MEDIA_ROOT=self._media)
        self._media_override.enable()
        self.addCleanup(self._media_override.disable)
        self.user = get_user_model().objects.create_user(username="farmer2", password="secret1234")
        self.client.force_login(self.user)

    def test_dashboard_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("farm:dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_create_plant_generates_reminders(self):
        response = self.client.post(reverse("farm:plant_save_ajax"), {
            "name": "Lettuce", "planting_date": date.today().isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        plant = Plant.objects.get(user=self.user, name="Lettuce")
        self.assertEqual(plant.reminders.count(), 3)

    def test_daily_check_marks_reminder_done(self):
        plant = Plant.objects.create(user=self.user, name="Lettuce", planting_date=date.today())
        rem = Reminder.objects.create(
            user=self.user, plant=plant, kind="water",
            message="Water the lettuce today", due_date=date.today(),
        )
        self.client.post(reverse("farm:dailycheck_save_ajax", args=[plant.id]), {
            "date": date.today().isoformat(), "watered": "true", "health": "good",
        })
        rem.refresh_from_db()
        self.assertTrue(rem.is_done)

    def test_care_log_create(self):
        plant = Plant.objects.create(user=self.user, name="Pepper")
        response = self.client.post(reverse("farm:carelog_save_ajax", args=[plant.id]), {
            "category": "pest", "description": "Aphids spotted",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(CareLog.objects.filter(plant=plant).exists())

    def test_care_log_photo_upload(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        plant = Plant.objects.create(user=self.user, name="Pepper")
        gif = (b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
               b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;')
        photo = SimpleUploadedFile("growth.gif", gif, content_type="image/gif")
        response = self.client.post(reverse("farm:carelog_save_ajax", args=[plant.id]), {
            "category": "growth", "description": "First leaves", "photo": photo,
        })
        self.assertEqual(response.status_code, 200)
        log = CareLog.objects.get(plant=plant)
        self.assertTrue(log.photo.name.startswith("care_photos/"))
        self.assertTrue(response.json()["photo_url"].endswith(".gif"))

    def test_care_log_rejects_non_image(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        plant = Plant.objects.create(user=self.user, name="Pepper")
        bad = SimpleUploadedFile("note.txt", b"hello", content_type="text/plain")
        response = self.client.post(reverse("farm:carelog_save_ajax", args=[plant.id]), {
            "category": "note", "description": "x", "photo": bad,
        })
        self.assertEqual(response.status_code, 400)


class FarmQuickLogTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="quick", password="secret1234")
        self.area = GardenArea.objects.create(user=self.user, name="Bed 1", rows=2, cols=2)
        self.p1 = Plant.objects.create(user=self.user, name="Lettuce", area=self.area,
                                       planting_date=date.today())
        self.p2 = Plant.objects.create(user=self.user, name="Tomato",
                                       planting_date=date.today())
        self.client.force_login(self.user)

    def _ajax(self, url, data=None):
        return self.client.post(url, data or {}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    def test_water_all_creates_checks_and_clears_reminders(self):
        Reminder.objects.create(user=self.user, plant=self.p1, kind="water",
                                message="Water", due_date=date.today())
        response = self._ajax(reverse("farm:quick_water_all"))
        self.assertEqual(response.json()["touched"], 2)
        self.assertTrue(DailyCheck.objects.filter(plant=self.p1, watered=True).exists())
        self.assertTrue(DailyCheck.objects.filter(plant=self.p2, watered=True).exists())
        self.assertTrue(Reminder.objects.get(plant=self.p1).is_done)

    def test_water_area_scoped(self):
        response = self._ajax(reverse("farm:quick_water_all"), {"area": self.area.id})
        self.assertEqual(response.json()["touched"], 1)
        self.assertFalse(DailyCheck.objects.filter(plant=self.p2).exists())

    def test_fertilize_all(self):
        response = self._ajax(reverse("farm:quick_fertilize_all"))
        self.assertEqual(response.json()["touched"], 2)
        self.assertTrue(DailyCheck.objects.filter(plant=self.p1, fertilized=True).exists())

    def test_pest_quick_log(self):
        response = self._ajax(reverse("farm:quick_pest"), {"plant": self.p1.id})
        self.assertEqual(response.status_code, 200)
        log = CareLog.objects.get(plant=self.p1)
        self.assertEqual(log.category, "pest")

    def test_quick_log_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.post(reverse("farm:quick_water_all")).status_code, 302)

    def test_dashboard_shows_quick_log(self):
        self.assertContains(self.client.get(reverse("farm:dashboard")), "Quick log")

    def test_area_create(self):
        response = self.client.post(reverse("farm:area_save_ajax"), {
            "name": "Bed A", "kind": "raised_bed", "rows": 4, "cols": 4,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(GardenArea.objects.filter(user=self.user, name="Bed A").exists())

    def test_plant_list_provides_plot_picker_data(self):
        area = GardenArea.objects.create(user=self.user, name="Bed", rows=2, cols=3)
        Plant.objects.create(user=self.user, name="Lettuce", area=area,
                             pos_x=1, pos_y=0, planting_date=date.today())
        response = self.client.get(reverse("farm:plant_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bed (2×3")
        self.assertContains(response, "cellPicker")
        self.assertContains(response, "Lettuce")


def _fake_forecast_response(rain_mm_per_slot):
    """Build a fake urlopen context manager returning forecast JSON."""
    import io
    import json

    payload = {"list": [{"rain": {"3h": rain_mm_per_slot}} for _ in range(8)]}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(payload).encode()

    return FakeResp()


class FarmWeatherTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = get_user_model().objects.create_user(username="weather", password="secret1234")

    def test_rain_sums_next_24h(self):
        from apps.farm import weather as farm_weather
        self.assertEqual(farm_weather.rain_next_24h({"list": [{"rain": {"3h": 2.0}}] * 8}), 16.0)
        self.assertEqual(farm_weather.rain_next_24h(None), 0.0)
        self.assertEqual(farm_weather.rain_next_24h({"list": []}), 0.0)

    def test_unconfigured_without_api_key(self):
        from django.test import override_settings
        from apps.farm import weather as farm_weather
        with override_settings(OPENWEATHER_API_KEY="", FARM_WEATHER_PROVIDER="openweathermap"):
            self.assertEqual(farm_weather.weather_status()["state"], "unconfigured")

    def test_heavy_rain_postpones_water_only(self):
        from unittest import mock
        from django.test import override_settings
        from apps.farm import weather as farm_weather
        plant = Plant.objects.create(user=self.user, name="Lettuce", planting_date=date.today())
        water = Reminder.objects.create(user=self.user, plant=plant, kind="water",
                                        message="Water the lettuce today", due_date=date.today())
        fert = Reminder.objects.create(user=self.user, plant=plant, kind="fertilize",
                                       message="Fertilize", due_date=date.today())
        with override_settings(OPENWEATHER_API_KEY="key", FARM_WEATHER_PROVIDER="openweathermap", FARM_RAIN_SKIP_MM=5.0):
            with mock.patch("urllib.request.urlopen", return_value=_fake_forecast_response(2.0)):
                result = farm_weather.adjust_water_reminders(self.user)
        self.assertTrue(result["skipped"])
        self.assertEqual(result["adjusted"], 1)
        water.refresh_from_db()
        fert.refresh_from_db()
        self.assertEqual(water.due_date, date.today() + timedelta(days=1))
        self.assertTrue(water.weather_paused)
        self.assertEqual(fert.due_date, date.today())  # untouched
        self.assertFalse(fert.weather_paused)

    def test_no_rain_leaves_reminders_alone(self):
        from unittest import mock
        from django.test import override_settings
        from apps.farm import weather as farm_weather
        plant = Plant.objects.create(user=self.user, name="Lettuce", planting_date=date.today())
        water = Reminder.objects.create(user=self.user, plant=plant, kind="water",
                                        message="Water", due_date=date.today())
        with override_settings(OPENWEATHER_API_KEY="key", FARM_WEATHER_PROVIDER="openweathermap", FARM_RAIN_SKIP_MM=5.0):
            with mock.patch("urllib.request.urlopen", return_value=_fake_forecast_response(0.0)):
                result = farm_weather.adjust_water_reminders(self.user)
        self.assertFalse(result["skipped"])
        water.refresh_from_db()
        self.assertEqual(water.due_date, date.today())

    def test_network_failure_fails_soft(self):
        from unittest import mock
        from django.test import override_settings
        from apps.farm import weather as farm_weather
        with override_settings(OPENWEATHER_API_KEY="key"):
            with mock.patch("urllib.request.urlopen", side_effect=OSError("offline")):
                self.assertEqual(farm_weather.weather_status()["state"], "unavailable")

    def test_weather_adjust_view(self):
        from unittest import mock
        from django.test import override_settings
        self.client.force_login(self.user)
        plant = Plant.objects.create(user=self.user, name="Okra", planting_date=date.today())
        Reminder.objects.create(user=self.user, plant=plant, kind="water",
                                message="Water the okra today", due_date=date.today())
        with override_settings(OPENWEATHER_API_KEY="key", FARM_WEATHER_PROVIDER="openweathermap", FARM_RAIN_SKIP_MM=5.0):
            with mock.patch("urllib.request.urlopen", return_value=_fake_forecast_response(3.0)):
                response = self.client.post(reverse("farm:weather_adjust"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Reminder.objects.filter(plant=plant, weather_paused=True).exists())


def _fake_open_meteo_response(mm_per_hour, start=None):
    """Build a fake urlopen context manager returning Open-Meteo hourly JSON."""
    import io
    import json
    from datetime import datetime, timezone as dt_timezone

    start = start or datetime.now(dt_timezone.utc).replace(minute=0, second=0, microsecond=0)
    times = [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(48)]
    payload = {"hourly": {"time": times, "precipitation": [mm_per_hour] * 48}}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(payload).encode()

    return FakeResp()


class FarmOpenMeteoTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = get_user_model().objects.create_user(username="meteo", password="secret1234")

    def test_hourly_rain_sums_next_24h_only(self):
        from datetime import datetime, timezone as dt_timezone
        from apps.farm import weather as farm_weather
        now = datetime.now(dt_timezone.utc).replace(minute=0, second=0, microsecond=0)
        payload = {
            "hourly": {
                "time": [(now + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(48)],
                "precipitation": [1.0] * 48,
            }
        }
        self.assertEqual(farm_weather.rain_next_24h_open_meteo(payload, now=now), 24.0)
        self.assertEqual(farm_weather.rain_next_24h_open_meteo(None), 0.0)
        self.assertEqual(farm_weather.rain_next_24h_open_meteo({}), 0.0)

    def test_status_ok_without_api_key(self):
        from unittest import mock
        from apps.farm import weather as farm_weather
        with mock.patch("urllib.request.urlopen", return_value=_fake_open_meteo_response(0.0)):
            status = farm_weather.weather_status()
        self.assertEqual(status["state"], "ok")
        self.assertFalse(status["skip_watering"])

    def test_heavy_rain_postpones_via_open_meteo(self):
        from unittest import mock
        from django.test import override_settings
        from apps.farm import weather as farm_weather
        plant = Plant.objects.create(user=self.user, name="Lettuce", planting_date=date.today())
        water = Reminder.objects.create(user=self.user, plant=plant, kind="water",
                                        message="Water", due_date=date.today())
        with override_settings(FARM_WEATHER_PROVIDER="open-meteo", FARM_RAIN_SKIP_MM=5.0):
            with mock.patch("urllib.request.urlopen", return_value=_fake_open_meteo_response(1.0)):
                result = farm_weather.adjust_water_reminders(self.user)
        self.assertTrue(result["skipped"])
        self.assertEqual(result["adjusted"], 1)
        water.refresh_from_db()
        self.assertTrue(water.weather_paused)


class FarmGeminiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="gemini", password="secret1234")

    def _plant(self):
        return Plant.objects.create(user=self.user, name="Tomato", variety="Cherry",
                                    planting_date=date.today() - timedelta(days=30))

    def test_prompt_contains_plant_context(self):
        from apps.farm import ai_advice as gemini
        plant = self._plant()
        prompt = gemini.build_prompt(plant, [], [], {"state": "unavailable"})
        self.assertIn("Tomato", prompt)
        self.assertIn(str(plant.expected_harvest_date), prompt)

    def test_unconfigured_returns_error(self):
        from django.test import override_settings
        from apps.farm import ai_advice as gemini
        with override_settings(GEMINI_API_KEY=""):
            result = gemini.ask_gemini("hello")
        self.assertFalse(result["ok"])
        self.assertIn("GEMINI_API_KEY", result["error"])

    def test_success_parses_answer(self):
        import json
        from unittest import mock
        from django.test import override_settings
        from apps.farm import ai_advice as gemini

        payload = {"candidates": [{"content": {"parts": [{"text": "Water daily."}]}}]}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(payload).encode()

        with override_settings(GEMINI_API_KEY="key"):
            with mock.patch("urllib.request.urlopen", return_value=FakeResp()):
                result = gemini.ask_gemini("hello")
        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], "Water daily.")

    def test_network_failure_fails_soft(self):
        from unittest import mock
        from django.test import override_settings
        from apps.farm import ai_advice as gemini
        with override_settings(GEMINI_API_KEY="key"):
            with mock.patch("urllib.request.urlopen", side_effect=OSError("offline")):
                result = gemini.ask_gemini("hello")
        self.assertFalse(result["ok"])

    def test_view_requires_key(self):
        plant = self._plant()
        self.client.force_login(self.user)
        response = self.client.post(reverse("farm:ai_advice_ajax", args=[plant.id]))
        self.assertEqual(response.status_code, 400)

    def test_view_saves_advice_to_care_history(self):
        import json
        from unittest import mock
        from django.test import override_settings
        plant = self._plant()
        self.client.force_login(self.user)
        payload = {"candidates": [{"content": {"parts": [{"text": "Mulch the base."}]}}]}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(payload).encode()

        with override_settings(GEMINI_API_KEY="key"):
            with mock.patch("urllib.request.urlopen", return_value=FakeResp()):
                response = self.client.post(reverse("farm:ai_advice_ajax", args=[plant.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(CareLog.objects.filter(plant=plant, description__contains="Mulch").exists())

    def test_view_scoped_to_owner(self):
        other = get_user_model().objects.create_user(username="gemini_other", password="secret1234")
        plant = self._plant()
        self.client.force_login(other)
        response = self.client.post(reverse("farm:ai_advice_ajax", args=[plant.id]))
        self.assertEqual(response.status_code, 404)


class FarmOpenRouterTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="orouter", password="secret1234")

    def _fake_response(self, payload):
        import json

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(payload).encode()

        return FakeResp()

    def test_unconfigured_returns_error(self):
        from django.test import override_settings
        from apps.farm import ai_openrouter as orouter
        with override_settings(OPENROUTER_API_KEY=""):
            result = orouter.ask_openrouter("hello")
        self.assertFalse(result["ok"])
        self.assertIn("OPENROUTER_API_KEY", result["error"])

    def test_success_parses_answer(self):
        from unittest import mock
        from django.test import override_settings
        from apps.farm import ai_openrouter as orouter
        payload = {"choices": [{"message": {"content": "  Water at dawn. "}}]}
        with override_settings(OPENROUTER_API_KEY="key"):
            with mock.patch("urllib.request.urlopen", return_value=self._fake_response(payload)):
                result = orouter.ask_openrouter("hello")
        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], "Water at dawn.")

    def test_api_error_payload(self):
        from unittest import mock
        from django.test import override_settings
        from apps.farm import ai_openrouter as orouter
        payload = {"error": {"message": "No credits left"}}
        with override_settings(OPENROUTER_API_KEY="key"):
            with mock.patch("urllib.request.urlopen", return_value=self._fake_response(payload)):
                result = orouter.ask_openrouter("hello")
        self.assertFalse(result["ok"])
        self.assertIn("No credits", result["error"])

    def test_view_uses_openrouter_when_selected(self):
        import json
        from unittest import mock
        from django.test import override_settings
        plant = Plant.objects.create(user=self.user, name="Lettuce", planting_date=date.today())
        self.client.force_login(self.user)
        payload = {"choices": [{"message": {"content": "Mulch the rows."}}]}
        with override_settings(AI_PROVIDER="openrouter", OPENROUTER_API_KEY="key"):
            with mock.patch("urllib.request.urlopen", return_value=self._fake_response(payload)):
                response = self.client.post(reverse("farm:ai_advice_ajax", args=[plant.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["advice"], "Mulch the rows.")
        self.assertTrue(CareLog.objects.filter(plant=plant, description__contains="OpenRouter").exists())

    def test_view_requires_openrouter_key(self):
        from django.test import override_settings
        plant = Plant.objects.create(user=self.user, name="Lettuce", planting_date=date.today())
        self.client.force_login(self.user)
        with override_settings(AI_PROVIDER="openrouter", OPENROUTER_API_KEY=""):
            response = self.client.post(reverse("farm:ai_advice_ajax", args=[plant.id]))
        self.assertEqual(response.status_code, 400)


class FarmMapGridTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="mapper", password="secret1234")
        self.area = GardenArea.objects.create(user=self.user, name="Bed", rows=2, cols=3)
        self.client.force_login(self.user)

    def test_grid_places_plant_and_empty_cells(self):
        Plant.objects.create(user=self.user, name="Lettuce", area=self.area,
                             pos_x=1, pos_y=0, planting_date=date.today())
        response = self.client.get(reverse("farm:map"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertContains(response, "Lettuce")
        # 2x3 = 6 cells, 1 filled -> 5 empty markers
        self.assertEqual(content.count("· empty ·"), 5)

    def test_off_grid_plant_listed_as_overflow(self):
        Plant.objects.create(user=self.user, name="Tomato", area=self.area,
                             pos_x=9, pos_y=9, planting_date=date.today())
        response = self.client.get(reverse("farm:map"))
        self.assertContains(response, "Off-grid")

    def test_unplaced_plant_section(self):
        Plant.objects.create(user=self.user, name="Okra", planting_date=date.today())
        response = self.client.get(reverse("farm:map"))
        self.assertContains(response, "Unplaced plants")


class FarmCompanionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="companion", password="secret1234")
        self.area = GardenArea.objects.create(user=self.user, name="Bed", rows=3, cols=3)
        self.client.force_login(self.user)

    def test_bad_neighbors_flagged(self):
        from apps.farm.companion import analyze
        tomato = Plant.objects.create(user=self.user, name="Tomato", area=self.area,
                                      pos_x=0, pos_y=0, planting_date=date.today())
        potato = Plant.objects.create(user=self.user, name="Potatoes", area=self.area,
                                      pos_x=1, pos_y=0, planting_date=date.today())
        alerts = analyze([tomato, potato])
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["kind"], "bad")
        self.assertIn("blight", alerts[0]["reason"])

    def test_good_pairing_highlighted(self):
        from apps.farm.companion import pairing
        kind, reason = pairing("Marigolds", "TOMATO")
        self.assertEqual(kind, "good")
        self.assertIn("aphids", reason)

    def test_distant_plants_ignored(self):
        from apps.farm.companion import analyze
        tomato = Plant.objects.create(user=self.user, name="Tomato", area=self.area,
                                      pos_x=0, pos_y=0, planting_date=date.today())
        basil = Plant.objects.create(user=self.user, name="Basil", area=self.area,
                                     pos_x=2, pos_y=2, planting_date=date.today())
        self.assertEqual(analyze([tomato, basil]), [])

    def test_map_shows_alerts_and_badges(self):
        Plant.objects.create(user=self.user, name="Tomato", area=self.area,
                             pos_x=0, pos_y=0, planting_date=date.today())
        Plant.objects.create(user=self.user, name="Marigold", area=self.area,
                             pos_x=0, pos_y=1, planting_date=date.today())
        Plant.objects.create(user=self.user, name="Potato", area=self.area,
                             pos_x=1, pos_y=0, planting_date=date.today())
        response = self.client.get(reverse("farm:map"))
        self.assertContains(response, "⚠️")
        self.assertContains(response, "✨")
        self.assertContains(response, "blight")
        self.assertContains(response, "Marigold")


class FarmAdminOversightTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="overseer", password="secret1234", email="o@example.com")
        self.staff = get_user_model().objects.create_user(username="worker", password="secret1234")
        self.plant = Plant.objects.create(user=self.staff, name="Lettuce",
                                          planting_date=date.today())

    def test_admin_sees_staff_plant(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("farm:plant_list")), "Lettuce")
        self.assertEqual(
            self.client.get(reverse("farm:plant_detail", args=[self.plant.id])).status_code, 200)

    def test_staff_cannot_see_admin_plant(self):
        Plant.objects.create(user=self.admin, name="Secret Herb", planting_date=date.today())
        self.client.force_login(self.staff)
        self.assertNotContains(self.client.get(reverse("farm:plant_list")), "Secret Herb")

    def test_admin_edit_keeps_owner(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("farm:plant_save_ajax"), {
            "id": self.plant.id, "name": "Lettuce", "planting_date": date.today().isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        self.plant.refresh_from_db()
        self.assertEqual(self.plant.user, self.staff)

    def test_admin_can_delete_staff_care_log(self):
        log = CareLog.objects.create(user=self.staff, plant=self.plant,
                                     date=date.today(), category="note", description="x")
        self.client.force_login(self.admin)
        response = self.client.post(reverse("farm:carelog_delete_ajax", args=[log.id]))
        self.assertEqual(response.status_code, 200)
