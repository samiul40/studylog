"""Session-based dashboard analytics (v6)."""

import datetime

from django.db.models import Count, Sum
from django.db.models.functions import TruncWeek
from django.utils import timezone

from learning.models import StudySession
from learning.services.types import WeekActivity
from learning.services.utils import current_week_start, fmt_duration


def _get_session_week_stats(user) -> dict:
    """Count and minutes for logged sessions this week and last week (Mon–Sun)."""
    if user is None:
        return {
            "this_week_count": 0,
            "this_week_mins": 0,
            "last_week_count": 0,
            "last_week_mins": 0,
        }

    wk = current_week_start()
    prev_start = wk - datetime.timedelta(weeks=1)
    cur_end = wk + datetime.timedelta(weeks=1)

    session_qs = StudySession.objects.filter(user=user, status="logged")
    this_agg = session_qs.filter(
        date__gte=wk.date(), date__lt=cur_end.date()
    ).aggregate(count=Count("id"), mins=Sum("duration_minutes"))
    last_agg = session_qs.filter(
        date__gte=prev_start.date(), date__lt=wk.date()
    ).aggregate(count=Count("id"), mins=Sum("duration_minutes"))

    return {
        "this_week_count": this_agg["count"] or 0,
        "this_week_mins": this_agg["mins"] or 0,
        "last_week_count": last_agg["count"] or 0,
        "last_week_mins": last_agg["mins"] or 0,
    }


def _get_weekly_sessions_chart(user, n: int = 8) -> list[WeekActivity]:
    """Trailing n weeks of logged session counts, oldest→newest."""
    wk = current_week_start()
    n_weeks_ago = wk - datetime.timedelta(weeks=n - 1)

    if user is None:
        return [
            {
                "label": (n_weeks_ago + datetime.timedelta(weeks=i))
                .date()
                .strftime("%-d %b"),
                "count": 0,
                "is_current": i == n - 1,
                "height_pct": 0,
            }
            for i in range(n)
        ]

    raw = (
        StudySession.objects.filter(
            user=user,
            status="logged",
            date__gte=n_weeks_ago.date(),
        )
        .annotate(week=TruncWeek("date"))
        .values("week")
        .annotate(count=Count("id"))
    )
    # TruncWeek on DateField returns date, not datetime — no .date() needed
    weekly_map = {entry["week"]: entry["count"] for entry in raw}

    result = []
    for i in range(n):
        week_start = (n_weeks_ago + datetime.timedelta(weeks=i)).date()
        result.append(
            {
                "label": week_start.strftime("%-d %b"),
                "count": weekly_map.get(week_start, 0),
                "is_current": week_start == wk.date(),
            }
        )

    max_count = max((w["count"] for w in result), default=0)
    for w in result:
        w["height_pct"] = round(w["count"] / max_count * 100) if max_count else 0

    return result


def _get_recent_sessions(user, limit: int = 5) -> list:
    """Last `limit` logged sessions for the simple dashboard feed."""
    if user is None:
        return []

    sessions = (
        StudySession.objects.filter(user=user, status="logged")
        .select_related("activity", "resource")
        .order_by("-date", "-created_at")[:limit]
    )

    result = []
    for s in sessions:
        topic = s.topic or (s.resource.title if s.resource else "")
        result.append(
            {
                "activity_slug": s.activity.slug,
                "activity_name": s.activity.name,
                "topic": topic,
                "duration_minutes": s.duration_minutes,
                "duration_display": fmt_duration(s.duration_minutes),
                "is_resource": s.resource_id is not None,
                "resource_title": s.resource.title if s.resource else None,
            }
        )
    return result


def _get_heatmap_by_session_minutes(user) -> dict:
    """Full-year heatmap shaded by daily session minutes.

    Thresholds: 0 / <45 / <90 / <150 / ≥150 → levels 0–4 (matches Sessions page).
    """
    today = timezone.localdate()
    year = today.year
    jan1 = datetime.date(year, 1, 1)
    dec31 = datetime.date(year, 12, 31)

    if user is not None:
        raw = (
            StudySession.objects.filter(
                user=user,
                status="logged",
                date__gte=jan1,
                date__lte=dec31,
            )
            .values("date")
            .annotate(total_mins=Sum("duration_minutes"))
        )
        daily_map = {entry["date"]: entry["total_mins"] for entry in raw}
    else:
        daily_map = {}

    grid_start = jan1 - datetime.timedelta(days=jan1.weekday())
    days_after = (6 - dec31.weekday()) % 7
    grid_end = dec31 + datetime.timedelta(days=days_after)

    total_mins = 0
    active_days = 0
    weeks = []
    cur = grid_start

    while cur <= grid_end:
        week = []
        for d in range(7):
            day = cur + datetime.timedelta(days=d)
            in_year = day.year == year
            is_future = day > today
            mins = daily_map.get(day, 0) if (in_year and not is_future) else 0

            if in_year and not is_future and mins > 0:
                total_mins += mins
                active_days += 1
                if mins < 45:
                    level = 1
                elif mins < 90:
                    level = 2
                elif mins < 150:
                    level = 3
                else:
                    level = 4
            else:
                level = 0

            week.append(
                {
                    "date": day.isoformat() if in_year else "",
                    "label": day.strftime("%-d %b %Y") if in_year else "",
                    "mins": mins,
                    "level": level,
                    "in_year": in_year,
                    "show": in_year,
                }
            )
        weeks.append(week)
        cur += datetime.timedelta(weeks=1)

    month_labels = []
    for month in range(1, 13):
        m1 = datetime.date(year, month, 1)
        col = (m1 - grid_start).days // 7
        month_labels.append(
            {"label": m1.strftime("%b"), "col": col, "left_px": col * 16}
        )

    return {
        "year": year,
        "weeks": weeks,
        "month_labels": month_labels,
        "total_mins": total_mins,
        "active_days": active_days,
        "total_mins_display": fmt_duration(total_mins),
    }


def _get_study_streak_unified(unit_qs, user) -> int:
    """Consecutive days ending today (or yesterday) with any study activity.

    A day is active if it has ≥1 logged session OR any unit completion/progress.
    """
    today = timezone.localdate()

    session_days = set()
    if user is not None:
        session_days = set(
            StudySession.objects.filter(user=user, status="logged", date__lte=today)
            .values_list("date", flat=True)
            .distinct()
        )

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
    active_days = session_days | completed_days | progress_days

    start = today if today in active_days else today - datetime.timedelta(days=1)
    streak = 0
    day = start
    while day in active_days:
        streak += 1
        day -= datetime.timedelta(days=1)

    return streak


def _get_momentum_v2(session_week_stats: dict) -> dict:
    """Momentum card: sessions logged + study time this vs last week."""

    sess_this = session_week_stats["this_week_count"]
    sess_last = session_week_stats["last_week_count"]
    time_this = session_week_stats["this_week_mins"]
    time_last = session_week_stats["last_week_mins"]

    def _delta(this, last):
        if last == 0:
            return "new", 0
        pct = round((this - last) / last * 100)
        return ("up" if pct >= 0 else "down"), abs(pct)

    sess_dir, sess_pct = _delta(sess_this, sess_last)
    time_dir, time_pct = _delta(time_this, time_last)

    sess_max = max(sess_this, sess_last, 1)
    time_max = max(time_this, time_last, 1)

    return {
        "sess_this_week": sess_this,
        "sess_last_week": sess_last,
        "sess_delta_pct": sess_pct,
        "sess_delta_dir": sess_dir,
        "sess_this_pct": round(sess_this / sess_max * 100),
        "sess_last_pct": round(sess_last / sess_max * 100),
        "time_this_week": time_this,
        "time_last_week": time_last,
        "time_this_week_display": fmt_duration(time_this),
        "time_last_week_display": fmt_duration(time_last),
        "time_delta_pct": time_pct,
        "time_delta_dir": time_dir,
        "time_this_pct": round(time_this / time_max * 100),
        "time_last_pct": round(time_last / time_max * 100),
    }


def _build_greeting_headline(units_this_week: int, sessions_this_week: int) -> str:
    """Greeting sub-line for the v6 dashboard."""
    unit_label = "unit" if units_this_week == 1 else "units"
    sess_label = "session" if sessions_this_week == 1 else "sessions"
    return (
        f"You completed {units_this_week} {unit_label} "
        f"and logged {sessions_this_week} {sess_label} this week."
    )
