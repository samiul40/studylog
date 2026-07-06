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
from .study_session import (
    StudySessionCalendarView,
    StudySessionCreateView,
    StudySessionDayView,
    StudySessionDeleteView,
    StudySessionListView,
    StudySessionUpdateView,
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
    "StudySessionCalendarView",
    "StudySessionCreateView",
    "StudySessionDeleteView",
    "StudySessionDayView",
    "StudySessionListView",
    "StudySessionUpdateView",
    "YouTubePreviewView",
    "dashboard_view",
]
