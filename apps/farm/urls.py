from django.urls import path

from . import views

app_name = "farm"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("plants/", views.plant_list_page, name="plant_list"),
    path("plants/<int:pk>/", views.plant_detail_page, name="plant_detail"),
    path("areas/", views.area_list_page, name="area_list"),
    path("map/", views.map_view, name="map"),
    path("reminders/", views.reminder_list_page, name="reminder_list"),
    # AJAX
    path("ajax/plants/get/<int:pk>/", views.plant_get_ajax, name="plant_get_ajax"),
    path("ajax/plants/save/", views.plant_save_ajax, name="plant_save_ajax"),
    path("ajax/plants/delete/<int:pk>/", views.plant_delete_ajax, name="plant_delete_ajax"),
    path("ajax/plants/<int:pk>/generate-reminders/", views.plant_generate_reminders, name="plant_generate_reminders"),
    path("ajax/areas/save/", views.area_save_ajax, name="area_save_ajax"),
    path("ajax/areas/delete/<int:pk>/", views.area_delete_ajax, name="area_delete_ajax"),
    path("ajax/reminders/save/", views.reminder_save_ajax, name="reminder_save_ajax"),
    path("ajax/reminders/toggle/<int:pk>/", views.reminder_toggle_ajax, name="reminder_toggle_ajax"),
    path("ajax/reminders/delete/<int:pk>/", views.reminder_delete_ajax, name="reminder_delete_ajax"),
    path("weather/adjust/", views.weather_adjust, name="weather_adjust"),
    path("quick/water/", views.quick_water_all, name="quick_water_all"),
    path("quick/fertilize/", views.quick_fertilize_all, name="quick_fertilize_all"),
    path("quick/pest/", views.quick_pest, name="quick_pest"),
    path("ajax/plants/<int:pk>/ai-advice/", views.ai_advice_ajax, name="ai_advice_ajax"),
    path("ajax/plants/<int:pk>/carelogs/save/", views.carelog_save_ajax, name="carelog_save_ajax"),
    path("ajax/carelogs/delete/<int:pk>/", views.carelog_delete_ajax, name="carelog_delete_ajax"),
    path("ajax/plants/<int:pk>/checks/save/", views.dailycheck_save_ajax, name="dailycheck_save_ajax"),
    path("ajax/checks/delete/<int:pk>/", views.dailycheck_delete_ajax, name="dailycheck_delete_ajax"),
]
