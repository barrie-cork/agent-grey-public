"""
URL configuration for health check endpoints.
"""

from django.urls import path

from . import views

app_name = "health"

urlpatterns = [
    path("", views.health_check, name="health_check"),
    path("detailed/", views.detailed_health_check, name="detailed_health_check"),
    path("ready/", views.ready_check, name="ready_check"),
    path("cache/", views.cache_health_check, name="cache_health_check"),
    path("static-debug/", views.static_debug, name="static_debug"),
    path("static-test/", views.static_test, name="static_test"),
]
