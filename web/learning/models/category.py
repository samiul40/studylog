from django.conf import settings
from django.db import models
from django.db.models import CheckConstraint, Q, UniqueConstraint
from django.utils.text import slugify

from learning.models.querysets import CategoryQuerySet

SYSTEM_CATEGORIES = [
    ("science", "Science"),
    ("technology", "Technology"),
    ("mathematics", "Mathematics"),
    ("humanities", "Humanities"),
]


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, blank=True)
    is_system = models.BooleanField(
        default=False,
        help_text="System categories are pre-seeded and shared across all users.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="categories",
        help_text=(
            "Null for system categories; set to the owning user for custom categories."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CategoryQuerySet.as_manager()

    class Meta:
        db_table = "category"
        ordering = ["-is_system", "name"]
        verbose_name_plural = "categories"
        constraints = [
            UniqueConstraint(
                fields=["slug"],
                condition=Q(is_system=True),
                name="unique_system_category_slug",
            ),
            UniqueConstraint(
                fields=["slug", "user"],
                condition=Q(is_system=False),
                name="unique_user_category_slug",
            ),
            CheckConstraint(
                condition=Q(is_system=True, user__isnull=True)
                | Q(is_system=False, user__isnull=False),
                name="category_system_user_consistent",
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
