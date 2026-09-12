from typing import List

from django.db.models import Max, Sum
from django.db.models.functions import TruncMonth, TruncWeek

from learning.models import DailyUsageStat
from learning.services.types import UsageRow
from learning.services.utils import fmt_duration

# TruncWeek buckets from Monday, so a week is labelled by the Monday it starts.
# Each period reports the rolling window that matches its own length.
PERIODS = {
    "week": (TruncWeek, lambda d: f"{d.day} {d:%b %Y}", "active_users_7d", 7),
    "month": (TruncMonth, lambda d: f"{d:%b %Y}", "active_users_28d", 28),
}

DEFAULT_PERIOD = "month"


def get_usage_breakdown(period: str = DEFAULT_PERIOD, n: int = 12) -> List[UsageRow]:
    """The most recent n weeks or months of recorded usage, newest first."""
    trunc, label_for, users_field, window_days = PERIODS.get(
        period, PERIODS[DEFAULT_PERIOD]
    )

    rows = (
        DailyUsageStat.objects.annotate(bucket=trunc("date"))
        .values("bucket")
        .annotate(
            sessions=Sum("sessions_logged"),
            minutes=Sum("minutes_logged"),
            resources=Sum("resources_created"),
            # Both are already de-duplicated per day, so the period takes its
            # highest day rather than a sum that would count people twice.
            active_users=Max(users_field),
            total_accounts=Max("total_accounts"),
        )
        .order_by("-bucket")[:n]
    )

    return [
        UsageRow(
            label=label_for(row["bucket"]),
            sessions=row["sessions"],
            minutes=row["minutes"],
            minutes_display=fmt_duration(row["minutes"]),
            active_users=row["active_users"],
            total_accounts=row["total_accounts"],
            window_days=window_days,
            resources=row["resources"],
        )
        for row in rows
    ]
