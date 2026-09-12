from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import Count, Sum
from django.utils import timezone

from learning.models import DailyUsageStat, LearningResource, StudySession

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Create site-wide usage statistics for every day up to yesterday that "
        "has none yet. Recorded days are never rewritten, so deleting an "
        "account cannot change past totals."
    )

    def handle(self, *args, **options):
        yesterday = timezone.localdate() - timedelta(days=1)
        date = (
            StudySession.objects.order_by("date").values_list("date", flat=True).first()
        )
        if date is None:
            self.stdout.write("No sessions to roll up.")
            return

        recorded = set(DailyUsageStat.objects.values_list("date", flat=True))

        created = 0
        while date <= yesterday:
            if date not in recorded:
                self._create_stats(date)
                created += 1
            date += timedelta(days=1)

        if not created:
            self.stdout.write("Usage stats are already up to date.")
            return

        self.stdout.write(
            self.style.SUCCESS(f"Created usage stats for {created} day(s).")
        )

    def _create_stats(self, date):
        # Planned sessions are intentions, not study that happened — the
        # dashboard counts only logged ones, and so must these totals.
        session_stats = StudySession.objects.filter(
            date=date,
            status=StudySession.Status.LOGGED,
        ).aggregate(
            sessions_logged=Count("id"),
            minutes_logged=Sum("duration_minutes"),
            active_users=Count("user", distinct=True),
        )

        # A resource carries only a created_at timestamp, so its days are UTC
        # ones, where the session counters use the date the user picked.
        resources_created = LearningResource.objects.filter(
            created_at__date=date
        ).count()

        DailyUsageStat.objects.create(
            date=date,
            sessions_logged=session_stats["sessions_logged"],
            minutes_logged=session_stats["minutes_logged"] or 0,
            resources_created=resources_created,
            active_users=session_stats["active_users"],
            active_users_7d=self._active_users_within(date, days=7),
            active_users_28d=self._active_users_within(date, days=28),
            total_accounts=User.objects.filter(
                is_active=True, date_joined__date__lte=date
            ).count(),
        )

    def _active_users_within(self, date, days):
        """Distinct users who logged a session in the `days` ending on date."""
        return (
            StudySession.objects.filter(
                status=StudySession.Status.LOGGED,
                date__gt=date - timedelta(days=days),
                date__lte=date,
            )
            .values("user")
            .distinct()
            .count()
        )
