import random
from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.utils import timezone

from learning.management.commands._seed import (
    SEED_PREFIX,
    refuse_in_production,
    seeded_users,
)
from learning.management.commands.rollup_retention_cohorts import week_start

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Seed accounts with back-dated signup dates, spread across completed "
        "weekly cohorts. The first step of the seed_retention pipeline."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--weeks",
            type=int,
            default=12,
            help="How many completed signup weeks to fill (default 12).",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete previously seeded accounts first, and their data with them.",
        )
        parser.add_argument("--force", action="store_true", help="Run with DEBUG off.")

    def handle(self, *args, **options):
        if refuse_in_production(self, options["force"]):
            return

        if options["clear"]:
            deleted, _ = seeded_users().delete()
            self.stdout.write(f"Cleared {deleted} seeded record(s).")

        group, _ = Group.objects.get_or_create(name="Learning User")

        # Newest completed week first, walking back one Monday at a time. The
        # current week is skipped: it is still taking signups, so the rollup
        # will not record it either.
        last_complete = week_start(timezone.localdate()) - timedelta(days=7)

        created = 0
        for week in range(options["weeks"]):
            cohort_start = last_complete - timedelta(weeks=week)
            for _ in range(random.randint(6, 18)):
                if self._make_user(cohort_start, group):
                    created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created} account(s) across {options['weeks']} week(s)."
            )
        )

    def _make_user(self, cohort_start, group):
        """One account registered somewhere inside the cohort's week.

        Signups are spread over all seven days on purpose: a Sunday joiner's
        week 1 runs six days later than a Monday joiner's, which is the case
        the retention windows have to get right.
        """
        joined_on = cohort_start + timedelta(days=random.randint(0, 6))
        username = f"{SEED_PREFIX}{joined_on:%Y%m%d}_{random.randint(1000, 9999)}"
        if User.objects.filter(username=username).exists():
            return None

        joined = timezone.make_aware(
            datetime.combine(joined_on, time(hour=random.randint(8, 21)))
        )
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.invalid",
            password="seeded-not-a-real-account",
            date_joined=joined,
        )
        # Signup normally attaches this through allauth's signal, which
        # create_user doesn't fire.
        user.groups.add(group)
        return user
