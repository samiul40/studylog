from .dashboard import dashboard_view
from .feature_request import FeatureRequestView
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
    StudySessionDeleteAjaxView,
    StudySessionDeleteView,
    StudySessionListView,
    StudySessionMarkDoneView,
    StudySessionPatchView,
    StudySessionUpdateView,
)
from .youtube import YouTubePreviewView

__all__ = [
    "FeatureRequestView",
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
    "StudySessionDeleteAjaxView",
    "StudySessionDeleteView",
    "StudySessionDayView",
    "StudySessionListView",
    "StudySessionMarkDoneView",
    "StudySessionPatchView",
    "StudySessionUpdateView",
    "YouTubePreviewView",
    "dashboard_view",
]
