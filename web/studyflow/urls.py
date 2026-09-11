import debug_toolbar
from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from learning.views import FeatureRequestView

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include("pages.urls")),
    # Before the allauth include so it wins: email management lives on our
    # Settings page, which does the same job in the app's own design.
    path(
        "accounts/email/",
        RedirectView.as_view(pattern_name="settings", permanent=False),
        name="account_email_redirect",
    ),
    path("accounts/", include("allauth.urls")),
    path("accounts/", include("accounts.urls")),
    path("learning/", include("learning.urls")),
    path(
        "feature-request/",
        FeatureRequestView.as_view(),
        name="feature_request",
    ),
]


if settings.DEBUG:
    urlpatterns.append(path("__debug__/", include(debug_toolbar.urls)))
