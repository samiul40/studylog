import datetime

from django.db import models
from django.db.models import (
    Case,
    Count,
    ExpressionWrapper,
    F,
    IntegerField,
    Q,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.utils import timezone


class LearningResourceQuerySet(models.QuerySet):
    def for_user(self, user):
        return self.filter(user=user)

    def active(self):
        return self.filter(is_archived=False)

    def archived(self):
        return self.filter(is_archived=True)

    def with_progress(self):
        return self.annotate(
            total_units=Count("units"),
            completed_units=Count(
                "units",
                filter=Q(units__status="completed"),
            ),
        ).annotate(
            percentage=Case(
                When(total_units=0, then=Value(0)),
                default=ExpressionWrapper(
                    100.0 * F("completed_units") / F("total_units"),
                    output_field=IntegerField(),
                ),
            )
        )

    def with_weekly_units(self):
        """Annotate each resource with units completed in the last 7 days."""
        seven_days_ago = timezone.now() - datetime.timedelta(days=7)
        return self.annotate(
            units_this_week=Count(
                "units",
                filter=Q(
                    units__status="completed",
                    units__updated_at__gte=seven_days_ago,
                ),
            )
        )

    def with_time_logged(self):
        """
        Annotate each resource with total minutes of time actually logged:
        - completed units contribute their full duration_minutes
        - in-progress units contribute their video_progress_minutes
        """
        return self.annotate(
            time_logged_minutes=Sum(
                Case(
                    When(
                        units__status="completed",
                        then=Coalesce(F("units__duration_minutes"), Value(0)),
                    ),
                    When(
                        units__status="in_progress",
                        then=Coalesce(F("units__video_progress_minutes"), Value(0)),
                    ),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            )
        )
