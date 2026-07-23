from adminsortable2.admin import SortableAdminBase, SortableInlineAdminMixin
from django.contrib import admin

from learning.services.dashboard import get_dashboard_stats

from .models import LearningResource, LearningUnit, ResourceType, StudySession


class LearningUnitInline(SortableInlineAdminMixin, admin.TabularInline):
    model = LearningUnit
    extra = 0
    fields = (
        "order",
        "title",
        "duration_minutes",
        "status",
        "video_progress_minutes",
    )
    ordering = ("order",)


@admin.register(ResourceType)
class ResourceTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "content_kind", "is_system", "user")
    list_filter = ("content_kind", "is_system")
    search_fields = ("name", "slug", "user__username")
    readonly_fields = ("slug", "created_at")
    autocomplete_fields = ("user",)

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.is_system:
            return (
                "name",
                "slug",
                "content_kind",
                "is_system",
                "user",
                "created_at",
            )
        return self.readonly_fields


@admin.register(LearningResource)
class LearningResourceAdmin(SortableAdminBase, admin.ModelAdmin):
    list_display = ("title", "resource_type", "user", "progress", "created_at")
    list_filter = ("resource_type", "created_at")
    search_fields = ("title", "description", "user__username")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)
    inlines = [LearningUnitInline]
    date_hierarchy = "created_at"
    autocomplete_fields = ("user",)

    fieldsets = (
        (
            None,
            {
                "fields": ("user", "title", "resource_type", "description"),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Progress")
    def progress(self, obj):
        total = obj.units.count()
        if total == 0:
            return "0%"
        completed = obj.units.filter(status="completed").count()
        return f"{completed}/{total} ({int(completed / total * 100)}%)"


@admin.register(LearningUnit)
class LearningUnitAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "resource",
        "order",
        "status",
        "duration_minutes",
        "video_progress_minutes",
    )
    list_filter = ("status", "resource__resource_type")
    search_fields = ("title", "resource__title", "notes")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("resource", "order")
    autocomplete_fields = ("resource",)

    fieldsets = (
        (
            None,
            {"fields": ("resource", "title", "order", "status")},
        ),
        (
            "Progress",
            {
                "fields": (
                    "duration_minutes",
                    "video_progress_minutes",
                    "notes",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(StudySession)
class StudySessionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "activity",
        "display_label",
        "date",
        "status",
        "duration_minutes",
    )
    list_filter = ("status", "activity", "date")
    search_fields = ("title", "topic", "notes", "user__username")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-date", "-created_at")
    date_hierarchy = "date"
    autocomplete_fields = ("user", "resource", "unit")

    fieldsets = (
        (
            None,
            {"fields": ("user", "activity", "resource", "unit", "status")},
        ),
        (
            "Details",
            {"fields": ("date", "title", "topic", "duration_minutes", "notes")},
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )


original_index = admin.site.index


def custom_admin_index(request, extra_context=None):
    stats = get_dashboard_stats()
    if extra_context is None:
        extra_context = {}
    extra_context.update(stats)
    return original_index(request, extra_context=extra_context)


admin.site.index = custom_admin_index
