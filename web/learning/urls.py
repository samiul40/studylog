from django.urls import path

from .views import (
    LearningUnitCompleteReadingView,
    LearningUnitCreateView,
    LearningUnitDeleteView,
    LearningUnitInlinePatchView,
    LearningUnitReorderView,
    LearningUnitUpdateStatusView,
    LearningUnitUpdateView,
    ResourceArchiveListView,
    ResourceArchiveView,
    ResourceCreateView,
    ResourceDeleteView,
    ResourceDetailView,
    ResourceListView,
    ResourceUpdateView,
    YouTubePreviewView,
    dashboard_view,
)

app_name = "learning"

urlpatterns = [
    path("", ResourceListView.as_view(), name="resource_list"),
    path("<int:pk>/", ResourceDetailView.as_view(), name="resource_detail"),
    path("create/", ResourceCreateView.as_view(), name="resource_create"),
    path(
        "<int:pk>/edit/",
        ResourceUpdateView.as_view(),
        name="resource_update",
    ),
    path(
        "<int:pk>/delete/",
        ResourceDeleteView.as_view(),
        name="resource_delete",
    ),
    path(
        "<int:resource_pk>/units/add/",
        LearningUnitCreateView.as_view(),
        name="unit_create",
    ),
    path(
        "<int:resource_pk>/units/<int:unit_pk>/edit/",
        LearningUnitUpdateView.as_view(),
        name="unit_update",
    ),
    path(
        "<int:resource_pk>/units/<int:unit_pk>/delete/",
        LearningUnitDeleteView.as_view(),
        name="unit_delete",
    ),
    path(
        "<int:resource_pk>/units/<int:unit_pk>/patch/",
        LearningUnitInlinePatchView.as_view(),
        name="unit_inline_update",
    ),
    path(
        "<int:resource_pk>/units/reorder/",
        LearningUnitReorderView.as_view(),
        name="unit_reorder",
    ),
    path(
        "units/<int:pk>/toggle-status/",
        LearningUnitUpdateStatusView.as_view(),
        name="unit_update_status",
    ),
    path("youtube-preview/", YouTubePreviewView.as_view(), name="youtube_preview"),
    path(
        "units/<int:pk>/complete-reading/",
        LearningUnitCompleteReadingView.as_view(),
        name="unit_complete_reading",
    ),
    path("dashboard/", dashboard_view, name="dashboard"),
    path(
        "<int:pk>/archive/",
        ResourceArchiveView.as_view(),
        name="resource_archive",
    ),
    path(
        "archived/",
        ResourceArchiveListView.as_view(),
        name="resource_archive_list",
    ),
]
