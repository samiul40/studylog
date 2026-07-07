from django.conf import settings
from django.db import models
from django.urls import reverse

from learning.models.querysets import StudySessionQuerySet


class StudySession(models.Model):
    class ActivityType(models.TextChoices):
        # Auto-logged from resource progress
        VIDEO_WATCH = "video_watch", "Video watching"
        READING = "reading", "Reading chapter"
        # Manually logged (freeform sessions)
        FLASHCARDS = "flashcards", "Flashcards / Anki"
        PRACTICE = "practice", "Practice problems"
        PAST_PAPERS = "past_papers", "Past papers"
        REVIEW_NOTES = "review_notes", "Review notes"
        WRITING = "writing", "Writing / essays"

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
    date = models.DateField()
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.LOGGED,
    )
    activity_type = models.CharField(max_length=30, choices=ActivityType.choices)
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

    def __str__(self):
        label = self.get_activity_type_display()
        topic = self.topic or "(no topic)"
        return f"{label} — {topic} ({self.date})"

    def get_absolute_url(self):
        return reverse("learning:session_list")

    def to_dict(self):
        return {
            "id": self.id,
            "activity_type": self.activity_type,
            "activity_label": self.get_activity_type_display(),
            "status": self.status,
            "topic": self.topic,
            "resource_id": self.resource_id,
            "resource_title": self.resource.title if self.resource else None,
            "date": self.date.isoformat(),
            "duration_minutes": self.duration_minutes,
            "notes": self.notes,
        }
