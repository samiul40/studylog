import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from faker import Faker

from learning.management.commands._seed import refuse_in_production, seeded_users
from learning.management.commands.rollup_retention_cohorts import window_offsets
from learning.models import Activity, StudySession

# How sticky a user has to be to still be around at each checkpoint. Drawn
# once per user and compared against all four, so anyone retained at week 8
# was also retained at week 1 — real cohorts decay, they don't oscillate.
# The gaps give roughly 60 / 50 / 40 / 30 percent retention.
STICKINESS = {1: 0.40, 2: 0.50, 4: 0.60, 8: 0.70}


class Command(BaseCommand):
    help = (
        "Seed study sessions for the accounts from seed_users, placed relative "
        "to each account's own signup date so the retention checkpoints have "
        "something to find. The third step of the seed_retention pipeline."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete the seeded accounts' existing sessions first.",
        )
        parser.add_argument("--force", action="store_true", help="Run with DEBUG off.")

    def handle(self, *args, **options):
        if refuse_in_production(self, options["force"]):
            return

        self.fake = Faker()
        self.today = timezone.localdate()
        self.activities = list(Activity.objects.filter(is_system=True))

        if not self.activities:
            self.stderr.write(self.style.ERROR("No system activities. Migrate first."))
            return

        # Sessions hang off a resource, so the users worth seeding are the ones
        # seed_learning has already been through. Prefetched, or this is a
        # query per account.
        users = seeded_users().prefetch_related("learning_resources")

        if options["clear"]:
            deleted, _ = StudySession.objects.filter(user__in=users).delete()
            self.stdout.write(f"Cleared {deleted} seeded session(s).")

        created = skipped = 0
        for user in users:
            resources = list(user.learning_resources.all())
            if not resources:
                skipped += 1
                continue
            created += self._seed_for(user, resources)

        if skipped:
            self.stdout.write(
                f"Skipped {skipped} account(s) with no resource — "
                f"run seed_learning --seeded-users first."
            )
        self.stdout.write(self.style.SUCCESS(f"Seeded {created} session(s)."))

    def _seed_for(self, user, resources):
        """Sessions on the days this user happened to show up."""
        signup_date = timezone.localtime(user.date_joined).date()

        # Almost everyone studies in their first week. That is signing up, not
        # coming back, and days 0-6 sit outside every checkpoint window.
        days = random.sample(range(7), random.randint(0, 3))

        stickiness = random.random()
        for week, threshold in STICKINESS.items():
            if stickiness < threshold:
                continue
            opens, closes = window_offsets(week)
            days += random.sample(range(opens, closes + 1), random.randint(1, 3))

        return sum(
            self._log_session(user, random.choice(resources), signup_date, day)
            for day in days
        )

    def _log_session(self, user, resource, signup_date, day):
        """One session `day` days after signup, unless that day hasn't come."""
        date = signup_date + timedelta(days=day)
        if date > self.today:
            return 0

        StudySession.objects.create(
            user=user,
            resource=resource,
            activity=random.choice(self.activities),
            date=date,
            # Spelled out rather than left to the model default: the rollup
            # counts only logged sessions, so a change of default would
            # silently empty the cohorts.
            status=StudySession.Status.LOGGED,
            topic=self.fake.sentence(nb_words=3),
            duration_minutes=random.randint(15, 90),
        )
        return 1
