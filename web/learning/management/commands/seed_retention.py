from django.core.management import call_command
from django.core.management.base import BaseCommand

from learning.management.commands._seed import refuse_in_production
from learning.models import UserRetentionCohort


class Command(BaseCommand):
    help = (
        "Run the whole retention demo in order: accounts, resources, sessions, "
        "then the rollup. Each step is its own command and can be run alone; "
        "this is the shortcut. Development only.\n\n"
        "Use --clear to regenerate a demo dataset. Without it a re-run is "
        "additive: it adds fresh accounts and sessions, but every cohort "
        "figure already recorded stays frozen, so the new accounts show up in "
        "the size of weeks that have no row yet and nowhere else."
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
            help=(
                "Start over: drop the seeded accounts and every recorded "
                "cohort first. This is the way to regenerate the demo — "
                "recorded cohorts are immutable, so without it the old "
                "numbers stay exactly as they were."
            ),
        )
        parser.add_argument("--force", action="store_true", help="Run with DEBUG off.")

    def handle(self, *args, **options):
        if refuse_in_production(self, options["force"]):
            return

        clear = options["clear"]
        force = options["force"]

        if clear:
            cohorts, _ = UserRetentionCohort.objects.all().delete()
            self.stdout.write(f"Cleared {cohorts} cohort row(s).")

        call_command(
            "seed_users",
            weeks=options["weeks"],
            clear=clear,
            force=force,
            stdout=self.stdout,
        )
        call_command(
            "seed_learning", seeded_users=True, force=force, stdout=self.stdout
        )
        call_command("seed_sessions", clear=clear, force=force, stdout=self.stdout)
        call_command("rollup_retention_cohorts", stdout=self.stdout)

        self.stdout.write(
            self.style.SUCCESS(
                "Done. The cohorts are under Config → Retention cohorts in the admin."
            )
        )
