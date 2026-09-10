import debug_toolbar
from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from learning.views import FeatureRequestView

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include("pages.urls")),
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
