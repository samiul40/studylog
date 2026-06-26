from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .learning_resource import LearningResource


class LearningUnit(models.Model):
    """Represents a unit of learning within a resource, such as a video or article."""

    class StatusChoices(models.TextChoices):
        """Defines the possible statuses for a learning unit."""

        NOT_STARTED = "not_started", "Not Started"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"

    resource = models.ForeignKey(
        LearningResource,
        on_delete=models.CASCADE,
        related_name="units",
    )
    title = models.CharField(max_length=255)
    order = models.PositiveIntegerField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Total Duration (minutes)",
        help_text="How many minutes the video is in total.",
    )
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.NOT_STARTED,
    )
    video_progress_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Progress Watched (minutes)",
        help_text="How many minutes of the video have been watched.",
    )
    notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "learning_unit"
        ordering = ["order"]
        indexes = [
            models.Index(fields=["resource", "status"], name="lu_resource_status_idx"),
            models.Index(
                fields=["resource", "status", "updated_at"],
                name="lu_resource_status_updated_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    status__in=["not_started", "in_progress", "completed"]
                ),
                name="chk_status_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(video_progress_minutes__lte=models.F("duration_minutes"))
                    | models.Q(video_progress_minutes__isnull=True)
                    | models.Q(duration_minutes__isnull=True)
                ),
                name="chk_progress_lte_duration",
            ),
        ]

    def __str__(self):
        return f"{self.title} ({self.resource.title})"

    @property
    def is_status_locked(self):
        return self.video_progress_minutes is not None

    @property
    def progress_percent(self):
        if not self.duration_minutes or self.video_progress_minutes is None:
            return 0

        return int((self.video_progress_minutes / self.duration_minutes) * 100)

    def clean(self):
        """Ensure video progress does not exceed total duration."""
        if (
            self.video_progress_minutes is not None
            and self.duration_minutes is not None
            and self.video_progress_minutes > self.duration_minutes
        ):
            raise ValidationError(
                {"video_progress_minutes": "Progress cannot exceed total duration."}
            )

    def save(self, *args, **kwargs):
        self._set_order_if_missing()
        self._update_status_from_progress()
        self._update_completed_at()
        self.full_clean()
        super().save(*args, **kwargs)

    def _set_order_if_missing(self):
        """
        Set the order of the unit to be one more than the last unit if not already set.
        """
        if self.order is not None:
            return

        last_unit = (
            LearningUnit.objects.filter(resource=self.resource)
            .order_by("-order")
            .first()
        )
        self.order = 1 if not last_unit else last_unit.order + 1

    def _update_status_from_progress(self):
        """Automatically update status based on video progress."""

        if self.video_progress_minutes is None:
            return

        if self.video_progress_minutes == 0:
            self.status = self.StatusChoices.NOT_STARTED

        elif (
            self.duration_minutes is not None
            and self.video_progress_minutes >= self.duration_minutes
        ):
            self.status = self.StatusChoices.COMPLETED

        else:
            self.status = self.StatusChoices.IN_PROGRESS

    def to_inline_dict(self):
        """Compact dict for AJAX responses on the resource detail page."""
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "duration_minutes": self.duration_minutes,
            "video_progress_minutes": self.video_progress_minutes,
            "notes": self.notes,
            "progress_percent": self.progress_percent,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
        }

    def _update_completed_at(self):
        if self.status == self.StatusChoices.COMPLETED:
            if not self.completed_at:
                self.completed_at = timezone.now()
        else:
            self.completed_at = None
