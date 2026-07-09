"""Dashboard analytics package.

Public surface: ``get_dashboard_stats``.
Private helpers are re-exported so existing test imports remain valid.
"""

from learning.services.dashboard._orchestrator import get_dashboard_stats
from learning.services.dashboard._resource import (
    _get_backlog,
    _get_completed_resources_count,
    _get_month_stats,
    _get_resource_progress,
    _get_resource_types_with_counts,
    _get_resources_table,
    _get_resume_resource,
    _get_stale_resources,
    _get_video_time_invested,
    _get_weekly_activity,
    _get_weekly_summary,
)
from learning.services.dashboard._session import (
    _build_greeting_headline,
    _get_heatmap_by_session_minutes,
    _get_momentum_v2,
    _get_recent_sessions,
    _get_session_week_stats,
    _get_study_streak_unified,
    _get_weekly_sessions_chart,
)

__all__ = [
    "get_dashboard_stats",
    "_get_backlog",
    "_get_completed_resources_count",
    "_get_month_stats",
    "_get_resource_progress",
    "_get_resource_types_with_counts",
    "_get_resources_table",
    "_get_resume_resource",
    "_get_stale_resources",
    "_get_video_time_invested",
    "_get_weekly_activity",
    "_get_weekly_summary",
    "_build_greeting_headline",
    "_get_heatmap_by_session_minutes",
    "_get_momentum_v2",
    "_get_recent_sessions",
    "_get_session_week_stats",
    "_get_study_streak_unified",
    "_get_weekly_sessions_chart",
]
