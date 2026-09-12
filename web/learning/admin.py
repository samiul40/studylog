from adminsortable2.admin import SortableAdminBase, SortableInlineAdminMixin
from django.contrib import admin
from django.utils.text import Truncator

from learning.services.dashboard import get_dashboard_stats
from learning.services.usage import get_usage_breakdown

from .models import (
    Category,
    DailyUsageStat,
    FeatureRequest,
    LearningResource,
    LearningUnit,
    ResourceType,
    StudySession,
)


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


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_system", "user")
    list_filter = ("is_system",)
    search_fields = ("name", "slug", "user__username")
    readonly_fields = ("slug", "created_at")
    autocomplete_fields = ("user",)

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.is_system:
            return ("name", "slug", "is_system", "user", "created_at")
        return self.readonly_fields


@admin.register(LearningResource)
class LearningResourceAdmin(SortableAdminBase, admin.ModelAdmin):
    list_display = (
        "title",
        "resource_type",
        "category",
        "user",
        "progress",
        "created_at",
    )
    list_filter = ("resource_type", "category", "created_at")
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
                "fields": (
                    "user",
                    "title",
                    "resource_type",
                    "category",
                    "description",
                ),
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


@admin.register(FeatureRequest)
class FeatureRequestAdmin(admin.ModelAdmin):
    list_display = ("idea_preview", "user", "status", "created_at")
    list_editable = ("status",)
    list_filter = ("status", "created_at")
    search_fields = ("idea", "why", "user__username", "user__email")
    readonly_fields = ("user", "idea", "why", "created_at", "updated_at")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"

    fieldsets = (
        (
            None,
            {"fields": ("user", "status")},
        ),
        (
            "Suggestion",
            {"fields": ("idea", "why")},
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Idea", ordering="idea")
    def idea_preview(self, obj):
        return Truncator(obj.idea).chars(80)

    def has_add_permission(self, request):
        return False


@admin.register(DailyUsageStat)
class DailyUsageStatAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "resources_created",
        "sessions_logged",
        "minutes_logged",
        "users_on_the_day",
        "users_prior_7_days",
        "users_prior_28_days",
        "total_accounts",
    )
    ordering = ("-date",)
    date_hierarchy = "date"

    @admin.display(description="Users (on the day)", ordering="active_users")
    def users_on_the_day(self, obj):
        return obj.active_users

    @admin.display(description="Users (prior 7 days)", ordering="active_users_7d")
    def users_prior_7_days(self, obj):
        return obj.active_users_7d

    @admin.display(description="Users (prior 28 days)", ordering="active_users_28d")
    def users_prior_28_days(self, obj):
        return obj.active_users_28d

    # Rows are written only by rollup_usage_stats, and rewriting one would
    # defeat the point of keeping totals that outlive the accounts behind them.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


def unreviewed_feature_requests(request):
    """Sidebar badge: suggestions nobody has triaged yet.

    Runs on every admin page, so it stays a single count with no joins.
    """
    return FeatureRequest.objects.filter(
        status=FeatureRequest.StatusChoices.NEW
    ).count()


original_index = admin.site.index


def custom_admin_index(request, extra_context=None):
    stats = get_dashboard_stats()
    if extra_context is None:
        extra_context = {}
    extra_context.update(stats)
    period = "week" if request.GET.get("period") == "week" else "month"
    extra_context["usage_period"] = period
    extra_context["usage_rows"] = get_usage_breakdown(period)
    return original_index(request, extra_context=extra_context)


admin.site.index = custom_admin_index
