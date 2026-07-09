"""Public dashboard API — assembles stats from session and resource modules."""

from django.db.models import Count, F, Q

from learning.models import LearningResource, LearningUnit
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
from learning.services.types import DashboardStats
from learning.services.utils import (
    calculate_percentage,
    fmt_duration,
    fmt_duration_html,
)


def get_dashboard_stats(user=None, resource_type=None) -> DashboardStats:
    """Return dashboard statistics for the v6 sessions-driven dashboard."""

    resource_qs, unit_qs = _build_querysets(user, resource_type)

    total_resources = resource_qs.count()
    total_units = unit_qs.count()
    completed_units = unit_qs.filter(status="completed").count()
    incomplete_units = total_units - completed_units
    completion_rate = calculate_percentage(completed_units, total_units)

    resource_progress = _get_resource_progress(resource_qs)
    most_progress = max(resource_progress, key=lambda x: x["percent"], default=None)
    least_progress = min(resource_progress, key=lambda x: x["percent"], default=None)
    recent_resources = resource_qs.select_related("resource_type").order_by(
        "-created_at"
    )[:5]

    in_progress_count = (
        resource_qs.annotate(
            total_u=Count("units"),
            done_u=Count("units", filter=Q(units__status="completed")),
        )
        .filter(total_u__gt=0, done_u__gt=0)
        .exclude(total_u=F("done_u"))
        .count()
    )

    session_week_stats = _get_session_week_stats(user)
    session_weekly_chart = _get_weekly_sessions_chart(user, n=8)
    recent_sessions = _get_recent_sessions(user, limit=5)
    heatmap_sessions = _get_heatmap_by_session_minutes(user)

    weekly_summary = _get_weekly_summary(unit_qs)
    backlog = _get_backlog(unit_qs, total=total_units, completed=completed_units)
    study_streak = _get_study_streak_unified(unit_qs, user)
    month_started, month_finished = _get_month_stats(resource_qs)
    time_invested = _get_video_time_invested(user)
    stale_resources = _get_stale_resources(resource_qs)
    resources_table = _get_resources_table(resource_qs)
    completed_resources_count = _get_completed_resources_count(resource_qs)
    resume_resource = _get_resume_resource(resource_qs)

    momentum = _get_momentum_v2(
        session_week_stats=session_week_stats,
        resource_time_this_week=time_invested["resource_this_week"],
        resource_time_last_week=time_invested["resource_last_week"],
    )

    units_this_week = weekly_summary["units_completed"]
    sessions_this_week = session_week_stats["this_week_count"]
    greeting_headline = _build_greeting_headline(units_this_week, sessions_this_week)

    combined_this_week = (
        time_invested["resource_this_week"] + session_week_stats["this_week_mins"]
    )

    # Unit-based chart kept for admin dashboard compatibility
    weekly_activity = _get_weekly_activity(unit_qs)

    return {
        "total_resources": total_resources,
        "total_units": total_units,
        "completed_units": completed_units,
        "incomplete_units": incomplete_units,
        "completion_rate": completion_rate,
        "resource_progress": resource_progress,
        "most_progress": most_progress,
        "least_progress": least_progress,
        "recent_resources": recent_resources,
        "active_filter": resource_type,
        "resource_types_with_counts": _get_resource_types_with_counts(user),
        "weekly_summary": weekly_summary,
        "in_progress_count": in_progress_count,
        "study_streak": study_streak,
        "month_started": month_started,
        "month_finished": month_finished,
        "weekly_activity": weekly_activity,
        "backlog": backlog,
        "time_invested": time_invested,
        "stale_resources": stale_resources,
        "momentum": momentum,
        "session_week_stats": session_week_stats,
        "session_weekly_chart": session_weekly_chart,
        "recent_sessions": recent_sessions,
        "heatmap_sessions": heatmap_sessions,
        "greeting_headline": greeting_headline,
        "greeting_units": units_this_week,
        "greeting_sessions": sessions_this_week,
        "combined_study_time_this_week": fmt_duration(combined_this_week),
        "combined_study_time_this_week_html": fmt_duration_html(combined_this_week),
        "session_time_this_week": fmt_duration(session_week_stats["this_week_mins"]),
        "resource_time_this_week": fmt_duration(time_invested["resource_this_week"]),
        "resources_table": resources_table,
        "completed_resources_count": completed_resources_count,
        "resume_resource": resume_resource,
    }


def _build_querysets(user, resource_type):
    resource_qs = LearningResource.objects.active()
    unit_qs = LearningUnit.objects.filter(resource__is_archived=False)

    if user is not None:
        resource_qs = resource_qs.filter(user=user)
        unit_qs = unit_qs.filter(resource__user=user)

    if resource_type:
        resource_qs = resource_qs.filter(resource_type__slug=resource_type)
        unit_qs = unit_qs.filter(resource__resource_type__slug=resource_type)

    return resource_qs, unit_qs
