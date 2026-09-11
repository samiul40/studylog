# Django
from django.urls import path

from . import views

urlpatterns = [
    path("settings/", views.Settings.as_view(), name="settings"),
    path(
        "accept-terms/",
        views.AcceptTermsView.as_view(),
        name="accept_terms",
    ),
    path("set-timezone/", views.set_timezone, name="set_timezone"),
    path(
        "cancel-social-signup/",
        views.cancel_social_signup,
        name="cancel_social_signup",
    ),
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
