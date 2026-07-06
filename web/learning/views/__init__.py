from .dashboard import dashboard_view
from .learning_resource import (
    ResourceArchiveListView,
    ResourceArchiveView,
    ResourceCreateView,
    ResourceDeleteView,
    ResourceDetailView,
    ResourceListView,
    ResourceUpdateView,
)
from .learning_unit import (
    LearningUnitCompleteReadingView,
    LearningUnitCreateView,
    LearningUnitDeleteView,
    LearningUnitInlinePatchView,
    LearningUnitReorderView,
    LearningUnitUpdateStatusView,
    LearningUnitUpdateView,
)
from .youtube import YouTubePreviewView

__all__ = [
    "ResourceArchiveListView",
    "ResourceArchiveView",
    "ResourceCreateView",
    "ResourceDeleteView",
    "ResourceDetailView",
    "ResourceListView",
    "ResourceUpdateView",
    "LearningUnitCompleteReadingView",
    "LearningUnitCreateView",
    "LearningUnitDeleteView",
    "LearningUnitUpdateView",
    "LearningUnitReorderView",
    "LearningUnitUpdateStatusView",
    "LearningUnitInlinePatchView",
    "YouTubePreviewView",
    "dashboard_view",
]
