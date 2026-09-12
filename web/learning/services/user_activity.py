"""Per-user session figures for the admin's user detail page.

Scoped to one user at a time on purpose — nothing here is safe to call once
per row of a changelist.
"""

import datetime

from django.db.models import Count, Q, Sum
from django.utils import timezone

from learning.models import StudySession
from learning.services.types import UserActivity

ACTIVITY_WINDOW_DAYS = 28


def calculate_streaks(dates) -> tuple[int, int]:
    """Return (current, best) runs of consecutive days.

    Takes any iterable of dates; duplicates and ordering don't matter. The
    current streak has to end today or yesterday — a run that stopped before
    that is broken, however long it was. Yesterday counts so that someone who
    simply hasn't studied yet today doesn't watch their streak vanish.
    """
    days = sorted(set(dates))
    if not days:
        return 0, 0

    one_day = datetime.timedelta(days=1)
    best = run = 1
    for previous, day in zip(days, days[1:]):
        run = run + 1 if day - previous == one_day else 1
        best = max(best, run)

    # `run` is the length of the final run, so it is the current one — but
    # only if that run reaches up to today or yesterday.
    if days[-1] < timezone.localdate() - one_day:
        return 0, best
    return run, best


def get_user_activity(user) -> UserActivity:
    """Session totals, streaks and the latest session for one user."""
    window_start = timezone.localdate() - datetime.timedelta(days=ACTIVITY_WINDOW_DAYS)
    recent = Q(date__gte=window_start)
    logged = StudySession.objects.filter(user=user, status=StudySession.Status.LOGGED)

    totals = logged.aggregate(
        sessions_total=Count("pk"),
        minutes_total=Sum("duration_minutes"),
        sessions_28d=Count("pk", filter=recent),
        minutes_28d=Sum("duration_minutes", filter=recent),
    )
    sessions_total = totals["sessions_total"]
    minutes_total = totals["minutes_total"] or 0

    current_streak, best_streak = calculate_streaks(
        logged.values_list("date", flat=True)
    )

    return UserActivity(
        sessions_total=sessions_total,
        sessions_28d=totals["sessions_28d"],
        minutes_total=minutes_total,
        minutes_28d=totals["minutes_28d"] or 0,
        average_minutes=round(minutes_total / sessions_total) if sessions_total else 0,
        current_streak=current_streak,
        best_streak=best_streak,
        last_session=logged.select_related("activity", "resource")
        .order_by("-date", "-created_at")
        .first(),
        window_days=ACTIVITY_WINDOW_DAYS,
    )
