from django.conf import settings
from django.db import models
from django.db.models import CheckConstraint, Q, UniqueConstraint
from django.utils.text import slugify

from learning.models.querysets import ActivityQuerySet

SYSTEM_ACTIVITIES = [
    ("watch", "Watched"),
    ("read", "Read"),
    ("flashcards", "Flashcards / Anki"),
    ("practice", "Practice problems"),
    ("pastpapers", "Past papers"),
    ("review", "Review notes"),
    ("writing", "Writing / essays"),
]


class Activity(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, blank=True)
    is_system = models.BooleanField(
        default=False,
        help_text=("System activities are pre-seeded and shared across all users."),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="activities",
        help_text=(
            "Null for system activities; set to the owning user for custom activities."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ActivityQuerySet.as_manager()

    class Meta:
        db_table = "activity"
        ordering = ["-is_system", "name"]
        constraints = [
            UniqueConstraint(
                fields=["slug"],
                condition=Q(is_system=True),
                name="unique_system_activity_slug",
            ),
            UniqueConstraint(
                fields=["slug", "user"],
                condition=Q(is_system=False),
                name="unique_user_activity_slug",
            ),
            CheckConstraint(
                condition=Q(is_system=True, user__isnull=True)
                | Q(is_system=False, user__isnull=False),
                name="activity_system_user_consistent",
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
