import debug_toolbar
from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include("pages.urls")),
    path("accounts/", include("allauth.urls")),
    path("accounts/", include("accounts.urls")),
    path("learning/", include("learning.urls")),
]


if settings.DEBUG:
    urlpatterns.append(path("__debug__/", include(debug_toolbar.urls)))
