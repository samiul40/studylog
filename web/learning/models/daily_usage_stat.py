from django.db import models


class DailyUsageStat(models.Model):
    """Site-wide usage totals for one calendar day.

    Holds no link to a user, so deleting an account can't change past numbers.
    """

    date = models.DateField(unique=True)

    sessions_logged = models.PositiveIntegerField(default=0)
    minutes_logged = models.PositiveIntegerField(default=0)
    resources_created = models.PositiveIntegerField(default=0)

    # Distinct users who studied on the day, and in the trailing windows ending
    # on it. The windows are stored rather than derived because counts cannot be
    # de-duplicated across days once the underlying sessions are gone.
    active_users = models.PositiveIntegerField(default=0)
    active_users_7d = models.PositiveIntegerField(default=0)
    active_users_28d = models.PositiveIntegerField(default=0)
    total_accounts = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "daily_usage_stat"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.date}: {self.sessions_logged} sessions"
