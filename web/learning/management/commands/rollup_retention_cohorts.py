from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import Count, DateField, F
from django.db.models.functions import TruncDate, TruncWeek
from django.utils import timezone

from learning.models import RETENTION_WEEKS, StudySession, UserRetentionCohort

User = get_user_model()


def week_start(date):
    """The Monday of the week containing date."""
    return date - timedelta(days=date.weekday())


def window_offsets(week):
    """Days after signup that checkpoint `week` opens and closes, inclusive."""
    return 7 * week, 7 * week + 6


class Command(BaseCommand):
    help = (
        "Record weekly signup cohorts and how many of each came back to study "
        "at the 1, 2, 4 and 8 week checkpoints. A cohort is written once its "
        "signup week has ended and a checkpoint once its window has closed for "
        "every member. Nothing already recorded is ever rewritten, so a figure "
        "cannot change after the fact."
    )

    def handle(self, *args, **options):
        self.today = timezone.localdate()

        # The most recent week that has fully ended. A week still taking
        # signups would grow after its size was recorded.
        last_complete = week_start(self.today) - timedelta(days=7)

        created = self._create_cohorts(last_complete)
        filled = self._fill_checkpoints()

        if not created and not filled:
            self.stdout.write("Cohort retention is already up to date.")
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {created} cohort(s) and filled {filled} checkpoint(s)."
            )
        )

    def _create_cohorts(self, last):
        """Add a row for every ended signup week that has signups and no row.

        A week nobody joined in gets no row: a cohort is a group of people, and
        an empty one has no retention to measure.
        """
        recorded = set(
            UserRetentionCohort.objects.values_list("cohort_start", flat=True)
        )

        # One grouped query for every cohort's size rather than one per week.
        # Counts every account still on file when the week is recorded,
        # whatever its state — the cohort is a signup fact, not an
        # account-status one. Anyone deleted before this first runs is already
        # gone from the table and cannot be counted.
        sizes = (
            User.objects.annotate(
                cohort=TruncWeek("date_joined", output_field=DateField())
            )
            .values("cohort")
            .annotate(size=Count("pk"))
            .order_by()
        )

        missing = [
            UserRetentionCohort(cohort_start=row["cohort"], cohort_size=row["size"])
            for row in sizes
            if row["cohort"] <= last and row["cohort"] not in recorded
        ]
        UserRetentionCohort.objects.bulk_create(missing)
        return len(missing)

    def _fill_checkpoints(self):
        """Record every checkpoint that has come due and isn't recorded yet."""
        cohorts = list(UserRetentionCohort.objects.all())

        filled = 0
        changed = {}
        for week in RETENTION_WEEKS:
            pending = [
                cohort
                for cohort in cohorts
                if cohort.retained(week) is None and self._is_due(cohort, week)
            ]
            if not pending:
                continue

            # Bounded to the oldest cohort that still needs this checkpoint, so
            # a long-running site doesn't re-scan years of settled history.
            counts = self._retained_by_cohort(
                week, since=min(cohort.cohort_start for cohort in pending)
            )
            for cohort in pending:
                value = counts.get(cohort.cohort_start, 0)
                setattr(cohort, f"week_{week}_retained", value)
                changed[cohort.pk] = cohort
                filled += 1

        if changed:
            now = timezone.now()
            for cohort in changed.values():
                # bulk_update writes what is in memory, and auto_now only fires
                # on save(), so the timestamp has to be set by hand.
                cohort.updated_at = now
            UserRetentionCohort.objects.bulk_update(
                changed.values(),
                [f"week_{week}_retained" for week in RETENTION_WEEKS] + ["updated_at"],
            )
        return filled

    def _is_due(self, cohort, week):
        """Has the checkpoint's window closed for every member of the cohort?

        The window runs from each user's own signup date, so the last person to
        join — on the Sunday, six days after the cohort opened — is inside it
        longest. Recording once the Monday joiners are done would freeze a
        count the Sunday joiners never had the chance to appear in.
        """
        _, closes = window_offsets(week)
        return cohort.cohort_start + timedelta(days=6 + closes) < self.today

    def _retained_by_cohort(self, week, since):
        """Users per cohort with a logged session inside the week's window.

        One grouped query covering every cohort at once. The window bounds are
        computed per row from the user's own signup date, so no user or session
        is loaded into Python to be compared there.

        This reads the live tables, so a member deleted before the checkpoint
        comes due cannot be counted. Once written, the count is frozen.
        """
        opens, closes = window_offsets(week)

        rows = (
            User.objects.annotate(
                cohort=TruncWeek("date_joined", output_field=DateField()),
                signup_date=TruncDate("date_joined"),
            )
            .filter(
                cohort__gte=since,
                # Planned sessions are intentions, not study that happened —
                # the rest of the analytics counts only logged ones, and so
                # does coming back.
                study_sessions__status=StudySession.Status.LOGGED,
                study_sessions__date__gte=F("signup_date") + timedelta(days=opens),
                study_sessions__date__lte=F("signup_date") + timedelta(days=closes),
            )
            .values("cohort")
            # Distinct over users, so somebody who studied every day of the
            # window is still one person who came back.
            .annotate(retained=Count("pk", distinct=True))
            .order_by()
        )
        return {row["cohort"]: row["retained"] for row in rows}
