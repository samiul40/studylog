# --------------------------------------------------------------------------- #
# Dashboard v3 — analytics service                                            #
# --------------------------------------------------------------------------- #

import datetime
import math
from typing import List, Optional

from django.db.models import Count, F, Max, Q, Sum
from django.db.models.functions import TruncDate, TruncWeek
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
    backlog = _get_backlog(unit_qs)
    study_streak = _get_study_streak(unit_qs)
    month_started, month_finished = _get_month_stats(resource_qs)
    time_invested = _get_time_invested(user)
    stale_resources = _get_stale_resources(resource_qs)
    momentum = _get_momentum(unit_qs)
    heatmap = _get_heatmap(unit_qs)
    resources_table = _get_resources_table(resource_qs)
    greeting_headline = _get_greeting_headline(unit_qs)

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
        "weekly_completions": _get_weekly_completions(unit_qs),
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


def _get_weekly_completions(unit_qs) -> list:
    """
    8 weeks (oldest→newest), completed-unit count per week.

    Uses completed_at; falls back gracefully when field is null.
    """
    now = timezone.now()
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
            }
        )
    return result


# --------------------------------------------------------------------------- #
# v3 dashboard helpers                                                        #
# --------------------------------------------------------------------------- #


def _get_weekly_activity(unit_qs) -> List[WeekActivity]:
    """
    8 ISO weeks (oldest→newest) with per-week completed-unit counts.

    Includes is_current flag and proportional bar heights for the chart.
    """
    now = timezone.now()
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
    now = timezone.now()
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


def _get_backlog(unit_qs) -> BacklogStats:
    """Completed / in-progress / not-started breakdown across all units."""
    total = unit_qs.count()
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
    """Consecutive active days (≥1 unit completed), ending today or yesterday."""
    today = timezone.now().date()

    active_days = set(
        unit_qs.filter(status="completed", completed_at__date__lte=today)
        .values_list("completed_at__date", flat=True)
        .distinct()
    )

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
    now = timezone.now()
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

    now = timezone.now()
    week_start = (now - datetime.timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    video_units = LearningUnit.objects.filter(
        resource__user=user,
        resource__is_archived=False,
        resource__resource_type__content_kind="video",
        status="completed",
        duration_minutes__isnull=False,
    )

    def _sum(qs):
        return qs.aggregate(t=Sum("duration_minutes"))["t"] or 0

    this_week_min = _sum(video_units.filter(completed_at__gte=week_start))
    this_month_min = _sum(video_units.filter(completed_at__gte=month_start))
    all_time_min = _sum(video_units)

    return {
        "this_week": _fmt_duration(this_week_min),
        "this_week_raw": this_week_min,
        "this_month": _fmt_duration(this_month_min),
        "all_time": _fmt_duration(all_time_min),
    }


def _get_stale_resources(resource_qs) -> List[StaleResource]:
    """In-progress resources idle ≥ 14 days, most idle first (max 3)."""
    today = timezone.now().date()
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


def _get_momentum(unit_qs) -> MomentumStats:
    """This week vs last week: unit counts and time, with percentage deltas."""
    now = timezone.now()
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

    units_this = this_wk.count()
    units_last = last_wk.count()
    time_this = this_wk.aggregate(t=Sum("duration_minutes"))["t"] or 0
    time_last = last_wk.aggregate(t=Sum("duration_minutes"))["t"] or 0

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
    year = timezone.now().year
    today = timezone.now().date()
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
    """Per-resource pace, last activity, and estimated finish for the table."""
    today = timezone.now().date()
    since_28 = timezone.now() - datetime.timedelta(days=28)

    rows = (
        resource_qs.select_related("resource_type")
        .annotate(
            total_u=Count("units"),
            done_u=Count("units", filter=Q(units__status="completed")),
            last_completed_at=Max("units__completed_at"),
        )
        .filter(total_u__gt=0)
        .exclude(total_u=F("done_u"))
        .order_by(F("last_completed_at").desc(nulls_last=True))
    )

    pace_map = dict(
        LearningUnit.objects.filter(
            resource__in=rows,
            status="completed",
            completed_at__gte=since_28,
        )
        .values("resource_id")
        .annotate(cnt=Count("id"))
        .values_list("resource_id", "cnt")
    )

    result = []
    for r in rows:
        total = r.total_u
        done = r.done_u
        remaining = total - done
        pct = calculate_percentage(done, total)

        completed_28 = pace_map.get(r.id, 0)
        pace_float = completed_28 / 4.0

        pace_display = _pace_display(pace_float)

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

        if pace_float == 0 or total == 0:
            est = "no pace"
        else:
            weeks_left = remaining / pace_float
            finish = today + datetime.timedelta(weeks=weeks_left)
            months_out = (finish.year - today.year) * 12 + (finish.month - today.month)
            if months_out <= 3:
                est = f"≈ {finish.day} {finish.strftime('%b')}"
            else:
                est = f"≈ {finish.strftime('%b %Y')}"

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
                "pace_display": pace_display,
                "pace_float": pace_float,
                "last_activity": last_act,
                "idle_days": idle_days,
                "is_idle": is_idle,
                "est_finish": est,
                "url": r.get_absolute_url(),
            }
        )
    return result


def _get_greeting_headline(unit_qs) -> Optional[str]:
    """Units-completed headline for this week, or None if no activity."""
    now = timezone.now()
    week_start = (now - datetime.timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    n = unit_qs.filter(status="completed", completed_at__gte=week_start).count()
    if n > 0:
        label = "unit" if n == 1 else "units"
        return f"You completed {n} {label} this week."
    return None


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


def _pace_display(pace_float: float) -> str:
    """
    Whole-number pace string per the README spec.

    0 → "—"; >0 but <0.5 → "1 /wk"; else ceil → "N /wk".
    """
    if pace_float == 0:
        return "—"
    if pace_float < 0.5:
        return "1 /wk"
    return f"{math.ceil(pace_float)} /wk"
