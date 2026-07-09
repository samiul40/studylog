from django.conf import settings
from django.db import models
from django.db.models import Q, UniqueConstraint
from django.urls import reverse

from learning.models.querysets import StudySessionQuerySet


class StudySession(models.Model):
    class Status(models.TextChoices):
        LOGGED = "logged", "Logged"
        PLANNED = "planned", "Planned"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="study_sessions",
    )
    resource = models.ForeignKey(
        "LearningResource",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="study_sessions",
    )
    unit = models.ForeignKey(
        "LearningUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="unit_sessions",
    )
    activity = models.ForeignKey(
        "Activity",
        on_delete=models.PROTECT,
        related_name="sessions",
    )
    date = models.DateField()
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.LOGGED,
    )
    title = models.CharField(max_length=255, blank=True)
    topic = models.CharField(max_length=255, blank=True)
    duration_minutes = models.PositiveIntegerField()
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = StudySessionQuerySet.as_manager()

    class Meta:
        db_table = "study_session"
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["user", "date"], name="ss_user_date_idx"),
        ]
        constraints = [
            # Safety net: one auto-logged session per unit per day (watch/read).
            # The upsert service owns deduplication logic; the FK can't be used
            # in a partial index by slug so we key on unit + date instead.
            UniqueConstraint(
                fields=["unit", "date"],
                condition=Q(status="logged", unit__isnull=False),
                name="ss_unit_date_logged_uniq",
            ),
        ]

    def __str__(self):
        label = self.activity.name
        topic = self.topic or "(no topic)"
        return f"{label} — {topic} ({self.date})"

    def get_absolute_url(self):
        return reverse("learning:session_list")

    @property
    def is_auto(self) -> bool:
        """True for system-created sessions (unit-linked read/watch activities)."""
        return self.unit_id is not None and self.activity.slug in ("read", "watch")

    def display_label(self):
        """Human-readable label: title if set, else activity (+ resource)."""
        if self.title:
            return self.title
        parts = [self.activity.name]
        if self.resource:
            parts.append(self.resource.title)
        return " · ".join(parts)

    def to_dict(self):
        return {
            "id": self.id,
            "activity_type": self.activity.slug,
            "activity_label": self.activity.name,
            "activity_id": self.activity_id,
            "title": self.title,
            "status": self.status,
            "topic": self.topic,
            "resource_id": self.resource_id,
            "resource_title": (self.resource.title if self.resource else None),
            "unit_id": self.unit_id,
            "unit_title": self.unit.title if self.unit else None,
            "date": self.date.isoformat(),
            "duration_minutes": self.duration_minutes,
            "notes": self.notes,
        }
