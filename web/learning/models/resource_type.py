from django.conf import settings
from django.db import models
from django.db.models import Q, UniqueConstraint
from django.utils.text import slugify


class ResourceType(models.Model):
    class ContentKind(models.TextChoices):
        VIDEO = "video", "Video / Audio"
        READING = "reading", "Reading"

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, blank=True)
    content_kind = models.CharField(
        max_length=20,
        choices=ContentKind.choices,
        default=ContentKind.VIDEO,
    )
    is_system = models.BooleanField(
        default=False,
        help_text="System types are pre-seeded and cannot be deleted.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="resource_types",
        help_text="Null for system types; set to the owning user for custom types.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "resource_type"
        ordering = ["-is_system", "name"]
        constraints = [
            UniqueConstraint(
                fields=["slug"],
                condition=Q(is_system=True),
                name="unique_system_resource_type_slug",
            ),
            UniqueConstraint(
                fields=["slug", "user"],
                condition=Q(is_system=False),
                name="unique_user_resource_type_slug",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def unit_label(self):
        if self.content_kind == self.ContentKind.READING:
            return "Chapter"
        return "Unit"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
