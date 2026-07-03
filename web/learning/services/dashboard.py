# --------------------------------------------------------------------------- #
# Dashboard v3 — analytics service                                            #
# --------------------------------------------------------------------------- #

import datetime
from typing import List, Optional

from django.db.models import Case, Count, F, IntegerField, Max, Q, Sum, Value, When
from django.db.models.functions import Coalesce, TruncDate, TruncWeek
from django.utils import timezone

from learning.models import LearningResource, LearningUnit, ResourceType

from .types import (
    BacklogStats,
    DashboardStats,
    HeatmapData,
    MomentumStats,
    ResourceProgress,
    ResourceTableRow,
    StaleResource,
    TimeInvested,
    WeekActivity,
    WeeklySummary,
)
from .utils import calculate_percentage

# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #


def get_dashboard_stats(user=None, resource_type=None) -> DashboardStats:
    """Return dashboard statistics for learning resources."""

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

    weekly_activity = _get_weekly_activity(unit_qs)
    weekly_summary = _get_weekly_summary(unit_qs)
    backlog = _get_backlog(unit_qs, total=total_units, completed=completed_units)
    study_streak = _get_study_streak(unit_qs)
    month_started, month_finished = _get_month_stats(resource_qs)
    time_invested = _get_time_invested(user)
    stale_resources = _get_stale_resources(resource_qs)
    momentum = _get_momentum(unit_qs, units_this_week=weekly_summary["units_completed"])
    heatmap = _get_heatmap(unit_qs)
    resources_table = _get_resources_table(resource_qs)
    greeting_headline = _get_greeting_headline(unit_qs)
    completed_resources_count = _get_completed_resources_count(resource_qs)
    resume_resource = _get_resume_resource(resource_qs)

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
        "heatmap": heatmap,
        "resources_table": resources_table,
        "greeting_headline": greeting_headline,
        "completed_resources_count": completed_resources_count,
        "resume_resource": resume_resource,
    }


# --------------------------------------------------------------------------- #
# Legacy helpers (pre-v3 — used by admin dashboard)                          #
# --------------------------------------------------------------------------- #


def _build_querysets(user, resource_type):
    """Apply user and resource type filters to the base querysets."""
    resource_qs = LearningResource.objects.active()
    unit_qs = LearningUnit.objects.filter(resource__is_archived=False)

    if user is not None:
        resource_qs = resource_qs.filter(user=user)
        unit_qs = unit_qs.filter(resource__user=user)

    if resource_type:
        resource_qs = resource_qs.filter(resource_type__slug=resource_type)
        unit_qs = unit_qs.filter(resource__resource_type__slug=resource_type)

    return resource_qs, unit_qs


def _get_resource_progress(resource_qs) -> List[ResourceProgress]:
    """Return per-resource completion percentages, sorted highest first."""
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
    """Return resource types with their resource counts for the given user."""
    if user is None:
        return []

    types = ResourceType.objects.filter(
        resources__user=user, resources__is_archived=False
    ).annotate(count=Count("resources"))
    return [{"type": rt, "count": rt.count} for rt in types]


# --------------------------------------------------------------------------- #
# v3 dashboard helpers                                                        #
# --------------------------------------------------------------------------- #


def _get_weekly_activity(unit_qs) -> List[WeekActivity]:
    """
    8 ISO weeks (oldest→newest) with per-week completed-unit counts.

    Includes is_current flag and proportional bar heights for the chart.
    """
    now = timezone.localtime()
    current_week_start = (now - datetime.timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    eight_weeks_ago = current_week_start - datetime.timedelta(weeks=7)

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
                "is_current": week_start.date() == current_week_start.date(),
            }
        )

    max_count = max((w["count"] for w in result), default=0)
    for w in result:
        w["height_pct"] = round(w["count"] / max_count * 100) if max_count else 0

    return result


def _get_weekly_summary(unit_qs) -> WeeklySummary:
    """Return stats for the current Monday–Sunday week."""
    now = timezone.localtime()
    week_start = (now - datetime.timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_end = week_start + datetime.timedelta(weeks=1)

    completed_this_week = unit_qs.filter(
        status="completed",
        completed_at__gte=week_start,
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
            "count": daily_map.get((week_start + datetime.timedelta(days=i)).date(), 0),
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
    """Completed / in-progress / not-started breakdown across all units.

    total/completed may be passed in to reuse counts the caller already
    has, avoiding a duplicate COUNT query for the same unit_qs.
    """
    if total is None:
        total = unit_qs.count()
    if completed is None:
        completed = unit_qs.filter(status="completed").count()
    in_progress = unit_qs.filter(status="in_progress").count()
    not_started = total - completed - in_progress
    pct = calculate_percentage(completed, total)

    completed_pct = calculate_percentage(completed, total)
    in_progress_pct = calculate_percentage(in_progress, total)
    not_started_pct = 100 - completed_pct - in_progress_pct

    return {
        "total": total,
        "completed": completed,
        "in_progress": in_progress,
        "not_started": not_started,
        "pct": pct,
        "completed_pct": completed_pct,
        "in_progress_pct": in_progress_pct,
        "not_started_pct": max(not_started_pct, 0),
    }


def _get_study_streak(unit_qs) -> int:
    """Consecutive active days, ending today or yesterday.

    A day is active if ≥1 unit was completed OR had any video progress recorded.
    """
    today = timezone.localdate()

    completed_days = set(
        unit_qs.filter(status="completed", completed_at__date__lte=today)
        .values_list("completed_at__date", flat=True)
        .distinct()
    )
    progress_days = set(
        unit_qs.filter(video_progress_minutes__gt=0, updated_at__date__lte=today)
        .values_list("updated_at__date", flat=True)
        .distinct()
    )
    active_days = completed_days | progress_days

    # Start from today; fall back to yesterday if today has no activity yet
    start = today if today in active_days else today - datetime.timedelta(days=1)
    streak = 0
    day = start
    while day in active_days:
        streak += 1
        day -= datetime.timedelta(days=1)

    return streak


def _get_month_stats(resource_qs) -> tuple:
    """(started, finished) resource counts for the current calendar month."""
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


def _get_time_invested(user) -> TimeInvested:
    """Video/audio minutes invested this ISO week, this month, and all time."""
    if user is None:
        return {
            "this_week": "—",
            "this_week_raw": 0,
            "this_month": "—",
            "all_time": "—",
        }

    now = timezone.localtime()
    week_start = (now - datetime.timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

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

    this_week_min = _sum_done(
        video_completed.filter(completed_at__gte=week_start)
    ) + _sum_prog(video_in_progress.filter(updated_at__gte=week_start))
    this_month_min = _sum_done(
        video_completed.filter(completed_at__gte=month_start)
    ) + _sum_prog(video_in_progress.filter(updated_at__gte=month_start))
    all_time_min = _sum_done(video_completed) + _sum_prog(video_in_progress)

    return {
        "this_week": _fmt_duration(this_week_min),
        "this_week_raw": this_week_min,
        "this_month": _fmt_duration(this_month_min),
        "all_time": _fmt_duration(all_time_min),
    }


def _get_stale_resources(resource_qs) -> List[StaleResource]:
    """In-progress resources idle ≥ 14 days, most idle first (max 3)."""
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


def _get_momentum(unit_qs, units_this_week=None) -> MomentumStats:
    """This week vs last week: unit counts and time, with percentage deltas.

    units_this_week may be passed in (e.g. from _get_weekly_summary, which
    covers the same Mon-Sun window) to avoid a duplicate COUNT query.
    """
    now = timezone.localtime()
    cur_start = (now - datetime.timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    prev_start = cur_start - datetime.timedelta(weeks=1)
    cur_end = cur_start + datetime.timedelta(weeks=1)

    this_wk = unit_qs.filter(
        status="completed",
        completed_at__gte=cur_start,
        completed_at__lt=cur_end,
    )
    last_wk = unit_qs.filter(
        status="completed",
        completed_at__gte=prev_start,
        completed_at__lt=cur_start,
    )

    units_this = units_this_week if units_this_week is not None else this_wk.count()
    units_last = last_wk.count()

    in_prog_this = unit_qs.filter(
        status="in_progress",
        video_progress_minutes__isnull=False,
        updated_at__gte=cur_start,
        updated_at__lt=cur_end,
    )
    in_prog_last = unit_qs.filter(
        status="in_progress",
        video_progress_minutes__isnull=False,
        updated_at__gte=prev_start,
        updated_at__lt=cur_start,
    )

    time_this = (this_wk.aggregate(t=Sum("duration_minutes"))["t"] or 0) + (
        in_prog_this.aggregate(t=Sum("video_progress_minutes"))["t"] or 0
    )
    time_last = (last_wk.aggregate(t=Sum("duration_minutes"))["t"] or 0) + (
        in_prog_last.aggregate(t=Sum("video_progress_minutes"))["t"] or 0
    )

    def _delta(this, last):
        if last == 0:
            return "new", 0
        pct = round((this - last) / last * 100)
        return ("up" if pct >= 0 else "down"), abs(pct)

    units_dir, units_pct = _delta(units_this, units_last)
    time_dir, time_pct = _delta(time_this, time_last)

    units_max = max(units_this, units_last, 1)
    time_max = max(time_this, time_last, 1)

    return {
        "units_this_week": units_this,
        "units_last_week": units_last,
        "units_delta_pct": units_pct,
        "units_delta_dir": units_dir,
        "units_this_pct": round(units_this / units_max * 100),
        "units_last_pct": round(units_last / units_max * 100),
        "time_this_week": time_this,
        "time_last_week": time_last,
        "time_this_week_display": _fmt_duration(time_this),
        "time_last_week_display": _fmt_duration(time_last),
        "time_delta_pct": time_pct,
        "time_delta_dir": time_dir,
        "time_this_pct": round(time_this / time_max * 100),
        "time_last_pct": round(time_last / time_max * 100),
    }


def _get_heatmap(unit_qs) -> HeatmapData:
    """Full-year activity heatmap data (Jan–Dec, Monday-start columns)."""
    today = timezone.localdate()
    year = today.year
    jan1 = datetime.date(year, 1, 1)
    dec31 = datetime.date(year, 12, 31)

    raw = (
        unit_qs.filter(
            status="completed",
            completed_at__date__gte=jan1,
            completed_at__date__lte=dec31,
        )
        .annotate(day=TruncDate("completed_at"))
        .values("day")
        .annotate(count=Count("id"))
    )
    daily_map = {entry["day"]: entry["count"] for entry in raw}

    # Grid starts on the Monday on or before Jan 1
    grid_start = jan1 - datetime.timedelta(days=jan1.weekday())
    # Grid ends on the Sunday on or after Dec 31
    days_after = (6 - dec31.weekday()) % 7
    grid_end = dec31 + datetime.timedelta(days=days_after)

    weeks = []
    cur = grid_start
    while cur <= grid_end:
        week = []
        for d in range(7):
            day = cur + datetime.timedelta(days=d)
            in_year = day.year == year
            is_future = day > today
            count = daily_map.get(day, 0) if (in_year and not is_future) else 0
            if not in_year or is_future or count == 0:
                level = 0
            elif count == 1:
                level = 1
            elif count == 2:
                level = 2
            elif count == 3:
                level = 3
            else:
                level = 4
            week.append(
                {
                    "date": day.isoformat() if in_year else "",
                    "label": (day.strftime("%-d %b %Y") if in_year else ""),
                    "count": count,
                    "level": level,
                    "in_year": in_year,
                    "show": in_year,
                }
            )
        weeks.append(week)
        cur += datetime.timedelta(weeks=1)

    # Month labels: column index where that month first appears
    month_labels = []
    for month in range(1, 13):
        month_start = datetime.date(year, month, 1)
        col = (month_start - grid_start).days // 7
        month_labels.append(
            {
                "label": month_start.strftime("%b"),
                "col": col,
                "left_px": col * 16,
            }
        )

    return {
        "year": year,
        "weeks": weeks,
        "month_labels": month_labels,
    }


def _get_resources_table(resource_qs) -> List[ResourceTableRow]:
    """Per-resource progress and last activity for the table."""
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

        is_idle = idle_days is not None and idle_days >= 14

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
                "is_idle": is_idle,
                "url": r.get_absolute_url(),
            }
        )
    return result


def _get_greeting_headline(unit_qs) -> Optional[str]:
    """Units-completed headline for this week, or None if no activity."""
    now = timezone.localtime()
    week_start = (now - datetime.timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    n = unit_qs.filter(status="completed", completed_at__gte=week_start).count()
    if n > 0:
        label = "unit" if n == 1 else "units"
        return f"You completed {n} {label} this week."
    return None


def _get_completed_resources_count(resource_qs) -> int:
    """Count resources where every unit is completed (pct = 100%)."""
    return (
        resource_qs.annotate(
            total_u=Count("units"),
            done_u=Count("units", filter=Q(units__status="completed")),
        )
        .filter(total_u__gt=0, total_u=F("done_u"))
        .count()
    )


def _get_resume_resource(resource_qs):
    """Most recently active in-progress resource, or None."""
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
    pct = calculate_percentage(row.done_u, row.total_u)
    return {
        "title": row.title,
        "type_name": row.resource_type.name,
        "type_slug": row.resource_type.slug,
        "content_kind": row.resource_type.content_kind,
        "pct": pct,
        "completed_units": row.done_u,
        "total_units": row.total_u,
        "url": row.get_absolute_url(),
    }


# --------------------------------------------------------------------------- #
# Private utilities                                                           #
# --------------------------------------------------------------------------- #


def _fmt_duration(minutes: int) -> str:
    """Format minutes as '2h 10m' / '45m' / '—' for zero."""
    if not minutes:
        return "—"
    h, m = divmod(int(minutes), 60)
    if h and m:
        return f"{h}h {m}m"
    if h:
        return f"{h}h"
    return f"{m}m"
