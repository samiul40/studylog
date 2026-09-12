from django.db import models


class DailyUsageStat(models.Model):
    """Site-wide usage totals for one calendar day.

    Holds no link to a user, so deleting an account can't change past numbers.
    """

    date = models.DateField(unique=True)

    sessions_logged = models.PositiveIntegerField(default=0)
    minutes_logged = models.PositiveIntegerField(default=0)
    active_users = models.PositiveIntegerField(default=0)
    resources_created = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "daily_usage_stat"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.date}: {self.sessions_logged} sessions"
