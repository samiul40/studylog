# Django
from django.urls import path

from . import views

urlpatterns = [
    path("settings/", views.Settings.as_view(), name="settings"),
    path("set-timezone/", views.set_timezone, name="set_timezone"),
    path(
        "delete-account/",
        views.DeleteAccountView.as_view(),
        name="delete_account",
    ),
    path(
        "reactivate/",
        views.ReactivateAccountView.as_view(),
        name="reactivate_account",
    ),
]
