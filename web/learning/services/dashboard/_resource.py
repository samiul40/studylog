"""Resource-based dashboard analytics."""

import datetime

from django.db.models import (
    Case,
    Count,
    F,
    IntegerField,
    Max,
    Q,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce, TruncDate, TruncWeek
from django.utils import timezone

from learning.models import LearningUnit, ResourceType
from learning.services.types import (
    BacklogStats,
    ResourceProgress,
    ResourceTableRow,
    StaleResource,
    WeekActivity,
    WeeklySummary,
)
from learning.services.utils import (
    calculate_percentage,
    current_week_start,
    fmt_duration,
)


def _get_resource_progress(resource_qs) -> list[ResourceProgress]:
    resources = resource_qs.annotate(
        total_units_count=Count("units"),
        completed_units_count=Count(
            "units",
            filter=Q(units__status="completed"),
        ),
    ).order_by("-created_at")[:5]

    progress = [
        {
            "id": r.id,
            "title": r.title,
            "percent": calculate_percentage(
                r.completed_units_count, r.total_units_count
            ),
        }
        for r in resources
    ]
    return sorted(progress, key=lambda x: x["percent"], reverse=True)


def _get_resource_types_with_counts(user) -> list:
    if user is None:
        return []
    types = ResourceType.objects.filter(
        resources__user=user, resources__is_archived=False
    ).annotate(count=Count("resources"))
    return [{"type": rt, "count": rt.count} for rt in types]


def _get_weekly_activity(unit_qs) -> list[WeekActivity]:
    """Unit-completion chart data (kept for admin dashboard compat)."""
    wk = current_week_start()
    eight_weeks_ago = wk - datetime.timedelta(weeks=7)

    raw = (
        unit_qs.filter(
            status="completed",
            completed_at__gte=eight_weeks_ago,
        )
        .annotate(week=TruncWeek("completed_at"))
        .values("week")
        .annotate(count=Count("id"))
    )
    weekly_map = {entry["week"].date(): entry["count"] for entry in raw}

    result = []
    for i in range(8):
        week_start = eight_weeks_ago + datetime.timedelta(weeks=i)
        result.append(
            {
                "label": week_start.strftime("%-d %b"),
                "count": weekly_map.get(week_start.date(), 0),
                "is_current": week_start.date() == wk.date(),
            }
        )

    max_count = max((w["count"] for w in result), default=0)
    for w in result:
        w["height_pct"] = round(w["count"] / max_count * 100) if max_count else 0

    return result


def _get_weekly_summary(unit_qs) -> WeeklySummary:
    wk = current_week_start()
    week_end = wk + datetime.timedelta(weeks=1)

    completed_this_week = unit_qs.filter(
        status="completed",
        completed_at__gte=wk,
        completed_at__lt=week_end,
    )

    units_completed = completed_this_week.count()
    learning_time_minutes = (
        completed_this_week.aggregate(total=Sum("duration_minutes"))["total"] or 0
    )
    resources_worked_on = completed_this_week.values("resource_id").distinct().count()

    raw_daily = (
        completed_this_week.annotate(day=TruncDate("completed_at"))
        .values("day")
        .annotate(count=Count("id"))
    )
    daily_map = {entry["day"]: entry["count"] for entry in raw_daily}

    day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    daily_completions = [
        {
            "label": day_labels[i],
            "count": daily_map.get((wk + datetime.timedelta(days=i)).date(), 0),
        }
        for i in range(7)
    ]

    return {
        "units_completed": units_completed,
        "learning_time_minutes": learning_time_minutes,
        "resources_worked_on": resources_worked_on,
        "daily_completions": daily_completions,
    }


def _get_backlog(unit_qs, total=None, completed=None) -> BacklogStats:
    if total is None:
        total = unit_qs.count()
    if completed is None:
        completed = unit_qs.filter(status="completed").count()
    in_progress = unit_qs.filter(status="in_progress").count()
    not_started = total - completed - in_progress

    completed_pct = calculate_percentage(completed, total)
    in_progress_pct = calculate_percentage(in_progress, total)
    not_started_pct = 100 - completed_pct - in_progress_pct

    return {
        "total": total,
        "completed": completed,
        "in_progress": in_progress,
        "not_started": not_started,
        "pct": completed_pct,
        "completed_pct": completed_pct,
        "in_progress_pct": in_progress_pct,
        "not_started_pct": max(not_started_pct, 0),
    }


def _get_month_stats(resource_qs) -> tuple:
    now = timezone.localtime()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    started = resource_qs.filter(created_at__gte=month_start).count()
    finished = (
        resource_qs.annotate(
            total_u=Count("units"),
            done_u=Count("units", filter=Q(units__status="completed")),
            last_completed_at=Max("units__completed_at"),
        )
        .filter(
            total_u__gt=0,
            last_completed_at__gte=month_start,
        )
        .filter(total_u=F("done_u"))
        .count()
    )
    return started, finished


def _get_video_time_invested(user) -> dict:
    """Video watch time this week, last week, this month, and all-time.

    Only counts video resources (content_kind='video'). Reading resources are
    excluded because their completion time is tracked via StudySession, not
    unit duration.
    """
    if user is None:
        return {
            "this_week": "—",
            "this_month": "—",
            "all_time": "—",
            "resource_this_week": 0,
            "resource_last_week": 0,
        }

    wk = current_week_start()
    prev_week_start = wk - datetime.timedelta(weeks=1)
    month_start = timezone.localtime().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )

    video_completed = LearningUnit.objects.filter(
        resource__user=user,
        resource__is_archived=False,
        resource__resource_type__content_kind="video",
        status="completed",
        duration_minutes__isnull=False,
    )
    video_in_progress = LearningUnit.objects.filter(
        resource__user=user,
        resource__is_archived=False,
        resource__resource_type__content_kind="video",
        status="in_progress",
        video_progress_minutes__isnull=False,
    )

    def _sum_done(qs):
        return qs.aggregate(t=Sum("duration_minutes"))["t"] or 0

    def _sum_prog(qs):
        return qs.aggregate(t=Sum("video_progress_minutes"))["t"] or 0

    resource_this_week = _sum_done(
        video_completed.filter(completed_at__gte=wk)
    ) + _sum_prog(video_in_progress.filter(updated_at__gte=wk))

    resource_last_week = _sum_done(
        video_completed.filter(completed_at__gte=prev_week_start, completed_at__lt=wk)
    ) + _sum_prog(
        video_in_progress.filter(updated_at__gte=prev_week_start, updated_at__lt=wk)
    )

    this_month_min = _sum_done(
        video_completed.filter(completed_at__gte=month_start)
    ) + _sum_prog(video_in_progress.filter(updated_at__gte=month_start))
    all_time_min = _sum_done(video_completed) + _sum_prog(video_in_progress)

    return {
        "this_week": fmt_duration(resource_this_week),
        "this_month": fmt_duration(this_month_min),
        "all_time": fmt_duration(all_time_min),
        "resource_this_week": resource_this_week,
        "resource_last_week": resource_last_week,
    }


def _get_stale_resources(resource_qs) -> list[StaleResource]:
    today = timezone.localdate()
    stale_cutoff = today - datetime.timedelta(days=14)

    rows = (
        resource_qs.select_related("resource_type")
        .annotate(
            total_u=Count("units"),
            done_u=Count("units", filter=Q(units__status="completed")),
            last_completed_at=Max("units__completed_at"),
        )
        .filter(total_u__gt=0, done_u__gt=0)
        .exclude(total_u=F("done_u"))
        .filter(last_completed_at__date__lte=stale_cutoff)
        .order_by("last_completed_at")
    )[:3]

    result = []
    for r in rows:
        idle_days = (today - r.last_completed_at.date()).days
        result.append(
            {
                "title": r.title,
                "type_name": r.resource_type.name,
                "type_slug": r.resource_type.slug,
                "content_kind": r.resource_type.content_kind,
                "idle_days": idle_days,
                "url": r.get_absolute_url(),
            }
        )
    return result


def _get_resources_table(resource_qs) -> list[ResourceTableRow]:
    today = timezone.localdate()

    rows = (
        resource_qs.select_related("resource_type")
        .annotate(
            total_u=Count("units"),
            done_u=Count("units", filter=Q(units__status="completed")),
            last_completed_at=Max("units__completed_at"),
            total_duration=Sum("units__duration_minutes"),
            time_done=Sum(
                Case(
                    When(
                        units__status="completed",
                        then=Coalesce(F("units__duration_minutes"), Value(0)),
                    ),
                    When(
                        units__status="in_progress",
                        then=Coalesce(F("units__video_progress_minutes"), Value(0)),
                    ),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            ),
        )
        .filter(total_u__gt=0)
        .exclude(total_u=F("done_u"))
        .order_by(F("last_completed_at").desc(nulls_last=True))
    )

    result = []
    for r in rows:
        total = r.total_u
        done = r.done_u
        total_dur = r.total_duration or 0
        time_done = r.time_done or 0
        pct = (
            calculate_percentage(time_done, total_dur)
            if total_dur > 0
            else calculate_percentage(done, total)
        )

        if r.last_completed_at:
            idle_days = (today - r.last_completed_at.date()).days
            if idle_days == 0:
                last_act = "today"
            elif idle_days == 1:
                last_act = "1d ago"
            else:
                last_act = f"{idle_days}d ago"
        else:
            idle_days = None
            last_act = "—"

        result.append(
            {
                "id": r.id,
                "title": r.title,
                "type_name": r.resource_type.name,
                "type_slug": r.resource_type.slug,
                "content_kind": r.resource_type.content_kind,
                "total_units": total,
                "completed_units": done,
                "pct": pct,
                "last_activity": last_act,
                "idle_days": idle_days,
                "is_idle": idle_days is not None and idle_days >= 14,
                "url": r.get_absolute_url(),
            }
        )
    return result


def _get_completed_resources_count(resource_qs) -> int:
    return (
        resource_qs.annotate(
            total_u=Count("units"),
            done_u=Count("units", filter=Q(units__status="completed")),
        )
        .filter(total_u__gt=0, total_u=F("done_u"))
        .count()
    )


def _get_resume_resource(resource_qs):
    row = (
        resource_qs.select_related("resource_type")
        .annotate(
            total_u=Count("units"),
            done_u=Count("units", filter=Q(units__status="completed")),
            last_completed_at=Max("units__completed_at"),
        )
        .filter(total_u__gt=0, done_u__gt=0)
        .exclude(total_u=F("done_u"))
        .order_by(F("last_completed_at").desc(nulls_last=True))
        .first()
    )
    if row is None:
        return None
    return {
        "title": row.title,
        "type_name": row.resource_type.name,
        "type_slug": row.resource_type.slug,
        "content_kind": row.resource_type.content_kind,
        "pct": calculate_percentage(row.done_u, row.total_u),
        "completed_units": row.done_u,
        "total_units": row.total_u,
        "url": row.get_absolute_url(),
    }
