from datetime import timedelta

from django.contrib import admin
from django.db.models import (
    Count,
    DateField,
    F,
    IntegerField,
    Max,
    OuterRef,
    Q,
    Subquery,
    Sum,
)
from django.db.models.functions import Coalesce
from django.utils import timezone
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
from learning.services.utils import fmt_duration

from .models import (
    Category,
    DailyUsageStat,
    FeatureRequest,
    LearningResource,
    LearningUnit,
    ResourceType,
    StudySession,
    UserRetentionCohort,
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


STALE_RESOURCE_DAYS = 30


class TractionFilter(DropdownFilter):
    """Which resources are actually being worked on."""

    title = "traction"
    parameter_name = "traction"

    def lookups(self, request, model_admin):
        return (
            ("this_week", "Studied this week"),
            ("stale", f"No session in {STALE_RESOURCE_DAYS} days"),
            ("never", "Never studied"),
            ("completed", "Completed"),
        )

    def queryset(self, request, queryset):
        today = timezone.localdate()
        lookups = {
            "this_week": Q(last_activity__gte=today - timedelta(days=7)),
            # Never-studied resources have no date to be stale, and get their
            # own bucket rather than being lumped in with the abandoned ones.
            "stale": Q(last_activity__lt=today - timedelta(days=STALE_RESOURCE_DAYS)),
            "never": Q(last_activity__isnull=True),
            "completed": Q(total_units__gt=0, completed_units=F("total_units")),
        }
        query = lookups.get(self.value())
        return queryset.filter(query) if query else queryset


@admin.register(LearningResource)
class LearningResourceAdmin(ModelAdmin):
    list_display = (
        "title",
        "resource_type",
        "category",
        "user",
        "progress",
        "get_session_count",
        "get_session_minutes",
        "get_last_activity",
        "created_at",
    )
    list_filter = (
        TractionFilter,
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

    def get_queryset(self, request):
        # with_progress() aggregates over units, so the session figures have to
        # come from subqueries: a second multi-valued join would multiply the
        # unit rows by the session rows and inflate both sides' sums.
        sessions = StudySession.objects.filter(resource=OuterRef("pk")).order_by()

        def over_sessions(aggregate, output_field):
            return Subquery(
                sessions.values("resource").annotate(value=aggregate).values("value"),
                output_field=output_field,
            )

        return (
            super()
            .get_queryset(request)
            # Three of the columns are foreign keys, so without this each row
            # costs three extra queries.
            .select_related("user", "resource_type", "category")
            .with_progress()
            .annotate(
                session_count=Coalesce(over_sessions(Count("pk"), IntegerField()), 0),
                session_minutes=Coalesce(
                    over_sessions(Sum("duration_minutes"), IntegerField()), 0
                ),
                last_activity=over_sessions(Max("date"), DateField()),
            )
        )

    @admin.display(description="Progress", ordering="percentage")
    def progress(self, obj):
        if not obj.total_units:
            return "0%"
        return f"{obj.completed_units}/{obj.total_units} ({obj.percentage}%)"

    @admin.display(description="Sessions", ordering="session_count")
    def get_session_count(self, obj):
        return obj.session_count

    @admin.display(description="Time logged", ordering="session_minutes")
    def get_session_minutes(self, obj):
        return fmt_duration(obj.session_minutes)

    @admin.display(description="Last activity", ordering="last_activity")
    def get_last_activity(self, obj):
        return obj.last_activity or "—"


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


@admin.register(UserRetentionCohort)
class UserRetentionCohortAdmin(ModelAdmin):
    """One row per signup week, with what became of the people in it.

    Percentages are worked out on the way to the page rather than stored, so
    they cannot drift from the counts they came from.
    """

    list_display = (
        "cohort_start",
        "cohort_size",
        "week_1_retained",
        "week_1_rate",
        "week_2_retained",
        "week_2_rate",
        "week_4_retained",
        "week_4_rate",
        "week_8_retained",
        "week_8_rate",
    )
    ordering = ("-cohort_start",)
    date_hierarchy = "cohort_start"

    # A checkpoint that hasn't elapsed is null, and 0% would read as nobody
    # coming back. This covers the retained columns and the rates alike.
    empty_value_display = "—"

    # The rate columns are deliberately not sortable: ordering them by the
    # count behind them would put a 9/10 cohort below a 20/200 one.
    @admin.display(description="Week 1 %")
    def week_1_rate(self, obj):
        return self._rate(obj, 1)

    @admin.display(description="Week 2 %")
    def week_2_rate(self, obj):
        return self._rate(obj, 2)

    @admin.display(description="Week 4 %")
    def week_4_rate(self, obj):
        return self._rate(obj, 4)

    @admin.display(description="Week 8 %")
    def week_8_rate(self, obj):
        return self._rate(obj, 8)

    def _rate(self, obj, week):
        rate = obj.retention_rate(week)
        # None falls through to empty_value_display, which is the honest answer
        # for an unelapsed checkpoint and for a cohort nobody joined.
        return None if rate is None else f"{rate}%"

    # Rows are written only by rollup_retention_cohorts, and editing one by
    # hand would defeat the point of figures that outlive the accounts behind
    # them.
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


def _usage_table(rows):
    """The usage rows shaped for Unfold's table component."""
    return {
        "headers": [
            "Period",
            "Resources",
            "Sessions",
            "Time",
            "Active users",
            "Accounts",
        ],
        "rows": [
            [
                row["label"],
                row["resources"],
                row["sessions"],
                row["minutes_display"],
                _share(row["active_users"], row["total_accounts"]),
                row["total_accounts"],
            ]
            for row in rows
        ],
    }


def _share(active, total):
    if not total:
        return active
    return f"{active} ({round(active / total * 100)}%)"


def dashboard_callback(request, context):
    """Inject the site-wide stats into Unfold's admin index.

    Wired up through UNFOLD["DASHBOARD_CALLBACK"] rather than by replacing
    admin.site.index, which is the hook Unfold provides for exactly this and
    survives the theme owning its own index view.
    """
    period = "week" if request.GET.get("period") == "week" else "month"
    usage_rows = get_usage_breakdown(period)

    context.update(get_dashboard_stats())
    context.update(
        {
            "usage_period": period,
            "periods": (("week", "Weekly"), ("month", "Monthly")),
            "usage_rows": usage_rows,
            "usage_table": _usage_table(usage_rows),
            "usage_window": 7 if period == "week" else 28,
            "stat_cards": [
                {"label": "Resources", "value": context["total_resources"]},
                {"label": "Units", "value": context["total_units"]},
                {"label": "Completed units", "value": context["completed_units"]},
                {
                    "label": "Completion rate",
                    "value": f"{context['completion_rate']}%",
                },
            ],
        }
    )
    return context
