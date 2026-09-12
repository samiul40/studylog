from datetime import timedelta

from django.conf import settings
from django.db import migrations


def backfill(apps, schema_editor):
    """Fill the rolling windows on rows written before those columns existed.

    Nothing ever rewrites a recorded day, so this is the only chance to compute
    them — once the sessions behind a day are deleted the counts are unknowable.
    """
    DailyUsageStat = apps.get_model("learning", "DailyUsageStat")
    StudySession = apps.get_model("learning", "StudySession")
    User = apps.get_model(settings.AUTH_USER_MODEL)

    def active_users_within(date, days):
        return (
            StudySession.objects.filter(
                status="logged",
                date__gt=date - timedelta(days=days),
                date__lte=date,
            )
            .values("user")
            .distinct()
            .count()
        )

    for stat in DailyUsageStat.objects.all():
        stat.active_users_7d = active_users_within(stat.date, 7)
        stat.active_users_28d = active_users_within(stat.date, 28)
        stat.total_accounts = User.objects.filter(
            is_active=True, date_joined__date__lte=stat.date
        ).count()
        stat.save(
            update_fields=["active_users_7d", "active_users_28d", "total_accounts"]
        )


class Migration(migrations.Migration):
    dependencies = [
        ("learning", "0037_dailyusagestat_active_users_28d_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
