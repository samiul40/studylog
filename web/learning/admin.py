from django.contrib import admin
from django.db.models import Q
from django.utils.text import Truncator
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import (
    ChoicesDropdownFilter,
    DropdownFilter,
    RelatedDropdownFilter,
)
from unfold.decorators import display

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


class LearningUnitInline(TabularInline):
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
    # Unfold draws its own drag handle for this field, so the resource page
    # keeps drag-reorder without adminsortable2's mixins.
    ordering_field = "order"


@admin.register(ResourceType)
class ResourceTypeAdmin(ModelAdmin):
    list_display = ("name", "slug", "content_kind", "is_system", "user")
    list_filter = (("content_kind", ChoicesDropdownFilter), "is_system")
    # Dropdown filters are form inputs, and Unfold only wraps the filter
    # panel in a <form> when this is on — without it the selects render
    # but selecting one does nothing.
    list_filter_submit = True
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
class CategoryAdmin(ModelAdmin):
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
class LearningResourceAdmin(ModelAdmin):
    list_display = (
        "title",
        "resource_type",
        "category",
        "user",
        "progress",
        "created_at",
    )
    list_filter = (
        ("resource_type", RelatedDropdownFilter),
        ("category", RelatedDropdownFilter),
        "created_at",
    )
    # Dropdown filters are form inputs, and Unfold only wraps the filter
    # panel in a <form> when this is on — without it the selects render
    # but selecting one does nothing.
    list_filter_submit = True
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
class LearningUnitAdmin(ModelAdmin):
    list_display = (
        "title",
        "resource",
        "order",
        "status",
        "duration_minutes",
        "video_progress_minutes",
    )
    list_filter = (
        ("status", ChoicesDropdownFilter),
        ("resource__resource_type", RelatedDropdownFilter),
    )
    # Dropdown filters are form inputs, and Unfold only wraps the filter
    # panel in a <form> when this is on — without it the selects render
    # but selecting one does nothing.
    list_filter_submit = True
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


# Colour groups the activity by study mode rather than giving each its own
# shade — Unfold has six label colours and users can add activities of their
# own, so anything unrecognised falls through to grey.
ACTIVITY_COLOURS = {
    "watch": "info",
    "read": "info",
    "flashcards": "warning",
    "review": "warning",
    "practice": "primary",
    "pastpapers": "primary",
    "writing": "success",
}

# Where a session stops being a long day and starts looking like a typo. The
# form only rejects durations under a minute, so nothing else catches these.
# Deliberately well above a normal long sitting — a past paper or a lecture
# block runs two to three hours, and flagging those would bury the real
# mistakes in legitimate rows.
LONG_SESSION_MINUTES = 240


class SessionQualityFilter(DropdownFilter):
    """Rows that are probably wrong rather than merely unusual."""

    title = "data quality"
    parameter_name = "quality"

    def lookups(self, request, model_admin):
        return (
            ("no_resource", "No resource linked"),
            ("long", f"Longer than {LONG_SESSION_MINUTES // 60} hours"),
            ("no_title", "No title"),
        )

    def queryset(self, request, queryset):
        lookups = {
            "no_resource": Q(resource__isnull=True),
            "long": Q(duration_minutes__gt=LONG_SESSION_MINUTES),
            "no_title": Q(title=""),
        }
        query = lookups.get(self.value())
        return queryset.filter(query) if query else queryset


@admin.register(StudySession)
class StudySessionAdmin(ModelAdmin):
    list_display = (
        "date",
        "user",
        "get_activity",
        "display_label",
        "get_context",
        "duration_minutes",
        "get_status",
    )
    list_filter = (
        SessionQualityFilter,
        ("status", ChoicesDropdownFilter),
        ("activity", RelatedDropdownFilter),
        "date",
    )
    # Dropdown filters are form inputs, and Unfold only wraps the filter
    # panel in a <form> when this is on — without it the selects render
    # but selecting one does nothing.
    list_filter_submit = True
    search_fields = ("title", "topic", "notes", "user__username")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-date", "-created_at")
    date_hierarchy = "date"
    autocomplete_fields = ("user", "resource", "unit")

    def get_queryset(self, request):
        # Every row reads its user, activity, resource and unit — display_label
        # alone touches two of them — so without this the page is four extra
        # queries per row.
        return (
            super()
            .get_queryset(request)
            .select_related("user", "activity", "resource", "unit")
        )

    @display(description="Activity", ordering="activity__name", label=ACTIVITY_COLOURS)
    def get_activity(self, obj):
        return obj.activity.slug, obj.activity.name

    @display(
        description="Status",
        ordering="status",
        label={
            StudySession.Status.LOGGED: "success",
            StudySession.Status.PLANNED: "info",
        },
    )
    def get_status(self, obj):
        return obj.status, obj.get_status_display()

    @admin.display(description="Resource / unit", ordering="resource__title")
    def get_context(self, obj):
        parts = [part.title for part in (obj.resource, obj.unit) if part]
        return " · ".join(parts) or "—"

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
class FeatureRequestAdmin(ModelAdmin):
    list_display = ("idea_preview", "user", "status", "created_at")
    list_editable = ("status",)
    list_filter = (("status", ChoicesDropdownFilter), "created_at")
    # Dropdown filters are form inputs, and Unfold only wraps the filter
    # panel in a <form> when this is on — without it the selects render
    # but selecting one does nothing.
    list_filter_submit = True
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
class DailyUsageStatAdmin(ModelAdmin):
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
