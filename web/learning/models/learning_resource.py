from django.conf import settings
from django.db import models
from django.urls import reverse

from .category import Category
from .querysets import LearningResourceQuerySet
from .resource_type import ResourceType


class LearningResource(models.Model):
    """Represents a user-owned learning resource."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="learning_resources",
    )
    title = models.CharField(max_length=255)
    resource_type = models.ForeignKey(
        ResourceType,
        on_delete=models.PROTECT,
        related_name="resources",
    )
    category = models.ForeignKey(
        Category,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resources",
        help_text=(
            "Optional grouping category. Resources with no category are "
            "shown under 'Other' on the resources list."
        ),
    )
    description = models.TextField(blank=True)
    url = models.URLField(
        blank=True,
        help_text="Optional link to the resource",
    )
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = LearningResourceQuerySet.as_manager()

    class Meta:
        db_table = "learning_resource"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_archived"], name="lr_user_archived_idx"),
        ]
        permissions = [
            (
                "view_dashboard",
                "Can view the dashboard with learning statistics",
            ),
        ]

    def __str__(self):
        return f"{self.title} - {self.user.username}"

    def get_absolute_url(self):
        return reverse("learning:resource_detail", kwargs={"pk": self.pk})
