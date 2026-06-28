# Django
from django.urls import path

from . import views

urlpatterns = [
    path("settings/", views.Settings.as_view(), name="settings"),
    path("set-timezone/", views.set_timezone, name="set_timezone"),
]
