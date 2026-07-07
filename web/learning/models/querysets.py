from django.db import models
from django.db.models import (
    Case,
    Count,
    ExpressionWrapper,
    F,
    IntegerField,
    Max,
    Q,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce


class StudySessionQuerySet(models.QuerySet):
    def for_user(self, user):
        return self.filter(user=user)

    def for_month(self, year: int, month: int):
        return self.filter(date__year=year, date__month=month)

    def dates_with_activity(self):
        return set(self.values_list("date", flat=True).distinct())


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
            total_duration=Sum("units__duration_minutes"),
            time_done=Sum(
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
            ),
        ).annotate(
            percentage=Case(
                When(
                    total_duration__gt=0,
                    then=ExpressionWrapper(
                        100.0 * F("time_done") / F("total_duration"),
                        output_field=IntegerField(),
                    ),
                ),
                When(total_units=0, then=Value(0)),
                default=ExpressionWrapper(
                    100.0 * F("completed_units") / F("total_units"),
                    output_field=IntegerField(),
                ),
            )
        )

    def with_status_order(self):
        """
        Annotate with status_order: 0=in_progress, 1=not_started, 2=completed.
        Also annotates last_unit_activity with the most recent unit updated_at.
        Requires with_progress() first (uses the percentage annotation).
        """
        return self.annotate(
            last_unit_activity=Max("units__updated_at"),
            status_order=Case(
                When(
                    Q(percentage__gt=0) & Q(percentage__lt=100),
                    then=Value(0),
                ),
                When(percentage=0, then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            ),
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
