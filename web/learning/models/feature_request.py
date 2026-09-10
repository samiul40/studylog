from django.conf import settings
from django.db import models


class FeatureRequest(models.Model):
    """A user-submitted product suggestion."""

    class StatusChoices(models.TextChoices):
        NEW = "new", "New"
        SHIPPED = "shipped", "Shipped"
        DECLINED = "declined", "Declined"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="feature_requests",
    )
    idea = models.CharField(max_length=2000)
    why = models.CharField(max_length=2000, blank=True)
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.NEW,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "feature_request"
        ordering = ["-created_at"]

    def __str__(self):
        who = self.user.username if self.user else "deleted user"
        return f"{self.idea[:40]} - {who}"
