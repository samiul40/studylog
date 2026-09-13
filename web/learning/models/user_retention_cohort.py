from django.db import models

# The checkpoints measured for every cohort, as whole weeks after signup.
# Week n covers days 7n to 7n+6 relative to each user's own signup date.
RETENTION_WEEKS = (1, 2, 4, 8)


class UserRetentionCohort(models.Model):
    """How many of one week's signups came back and studied later.

    Holds counts only, with no link to a user, so deleting an account cannot
    change a cohort that has already been recorded.

    A retained count is null until its window has fully elapsed for every
    member of the cohort. Zero would claim nobody came back, which is a very
    different statement from "we cannot know yet".
    """

    # The Monday the cohort's signup week began.
    cohort_start = models.DateField(unique=True)
    cohort_size = models.PositiveIntegerField(default=0)

    week_1_retained = models.PositiveIntegerField(null=True, blank=True)
    week_2_retained = models.PositiveIntegerField(null=True, blank=True)
    week_4_retained = models.PositiveIntegerField(null=True, blank=True)
    week_8_retained = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_retention_cohort"
        ordering = ["-cohort_start"]

    def __str__(self):
        return f"Week of {self.cohort_start}: {self.cohort_size} signups"

    def retained(self, week):
        """The recorded count for a checkpoint, or None if it hasn't elapsed."""
        return getattr(self, f"week_{week}_retained")

    def retention_rate(self, week):
        """Percentage retained at a checkpoint, or None if it can't be stated.

        Percentages are derived rather than stored so the two can never drift
        apart. An empty cohort has no rate — 0% would imply people didn't come
        back, when in fact nobody signed up.
        """
        retained = self.retained(week)
        if retained is None or not self.cohort_size:
            return None
        return round(retained / self.cohort_size * 100, 1)
