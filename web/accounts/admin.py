from datetime import timedelta

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialApp, SocialToken
from axes.models import AccessAttempt, AccessFailureLog, AccessLog
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.contrib.sites.models import Site
from django.db.models import Count, IntegerField, Max, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from unfold.admin import ModelAdmin, StackedInline
from unfold.contrib.filters.admin import DropdownFilter
from unfold.decorators import display

from learning.models import LearningResource

from .models import UserProfile

User = get_user_model()

CONSENT_FIELDS = (
    "terms_accepted",
    "terms_accepted_at",
    "terms_version",
    "privacy_accepted",
    "privacy_accepted_at",
    "privacy_version",
    "age_confirmed",
    "age_confirmed_at",
)

# Engagement bucket boundaries, in days.
ACTIVE_WITHIN = 7
IDLE_WITHIN = 30
NEW_JOINED_WITHIN = 14
NEW_MAX_SESSIONS = 3
ACTIVITY_WINDOW = 28

# Bucket key -> (column text, Unfold label colour).
ENGAGEMENT_BUCKETS = {
    "deletion": ("Deletion requested", "danger"),
    "new": ("New", "info"),
    "active": ("Active", "success"),
    "idle": ("Idle", "warning"),
    "dormant": ("Dormant", ""),
    "never": ("Never logged", ""),
}


def engagement_cutoffs():
    """The boundaries the column and the filter both read, resolved once."""
    today = timezone.localdate()
    return {
        "active": today - timedelta(days=ACTIVE_WITHIN),
        "idle": today - timedelta(days=IDLE_WITHIN),
        "joined": timezone.now() - timedelta(days=NEW_JOINED_WITHIN),
        "window": today - timedelta(days=ACTIVITY_WINDOW),
    }


def engagement_queries(cutoffs):
    """One Q per bucket, each excluding the buckets that outrank it.

    The buckets have to partition the table for the filter to agree with the
    column, so every bucket below "deletion" carries the exclusions above it.
    """
    deletion = Q(profile__deletion_requested_at__isnull=False)
    # A user who joined this fortnight has no sessions older than the 28-day
    # window, so sessions_28d is their lifetime count.
    new = Q(date_joined__gte=cutoffs["joined"], sessions_28d__lt=NEW_MAX_SESSIONS)
    settled = ~deletion & ~new

    return {
        "deletion": deletion,
        "new": ~deletion & new,
        "active": settled & Q(last_session__gte=cutoffs["active"]),
        "idle": settled
        & Q(last_session__lt=cutoffs["active"], last_session__gte=cutoffs["idle"]),
        "dormant": settled & Q(last_session__lt=cutoffs["idle"]),
        "never": settled & Q(last_session__isnull=True),
    }


def engagement_bucket(obj, cutoffs):
    """The bucket for one already-annotated row, in the same priority order."""
    try:
        requested_deletion = obj.profile.deletion_requested_at is not None
    except UserProfile.DoesNotExist:
        requested_deletion = False

    if requested_deletion:
        return "deletion"
    if (
        obj.date_joined >= cutoffs["joined"]
        and (obj.sessions_28d or 0) < NEW_MAX_SESSIONS
    ):
        return "new"
    if obj.last_session is None:
        return "never"
    if obj.last_session >= cutoffs["active"]:
        return "active"
    if obj.last_session >= cutoffs["idle"]:
        return "idle"
    return "dormant"


class EngagementFilter(DropdownFilter):
    title = "engagement"
    parameter_name = "engagement"

    def lookups(self, request, model_admin):
        return [(key, text) for key, (text, _colour) in ENGAGEMENT_BUCKETS.items()]

    def queryset(self, request, queryset):
        # Reads the annotations from UserAdmin.get_queryset, so the filter and
        # the column can never disagree about where a user falls.
        query = engagement_queries(engagement_cutoffs()).get(self.value())
        return queryset.filter(query) if query else queryset


class TermsStatusFilter(DropdownFilter):
    title = "terms status"
    parameter_name = "terms_status"

    def lookups(self, request, model_admin):
        return (
            ("current", "Accepted current version"),
            ("outdated", "Accepted an older version"),
            ("never", "Never accepted"),
        )

    def queryset(self, request, queryset):
        current = settings.TERMS_VERSION
        never = Q(profile__isnull=True) | Q(profile__terms_version="")

        if self.value() == "current":
            return queryset.filter(profile__terms_version=current)
        if self.value() == "outdated":
            return queryset.exclude(profile__terms_version=current).exclude(never)
        if self.value() == "never":
            return queryset.filter(never)
        return queryset


class UserProfileInline(StackedInline):
    model = UserProfile
    extra = 0
    # Consent is a record of something the user did. Editing it here would be
    # fabricating that record, so the whole block is read-only.
    readonly_fields = ("deletion_requested_at",) + CONSENT_FIELDS
    fields = ("timezone", "deletion_requested_at") + CONSENT_FIELDS


class UserAdmin(BaseUserAdmin, ModelAdmin):
    inlines = (UserProfileInline,)
    list_display = (
        "username",
        "email",
        "get_engagement",
        "get_last_session",
        "get_recent_activity",
        "get_resource_count",
        "date_joined",
        "get_terms_status",
    )
    list_filter = (
        EngagementFilter,
        TermsStatusFilter,
    ) + BaseUserAdmin.list_filter

    ordering = ("-date_joined",)

    def get_queryset(self, request):
        cutoffs = engagement_cutoffs()
        recent = Q(study_sessions__date__gte=cutoffs["window"])

        return (
            super()
            .get_queryset(request)
            # Without this each row fetches its profile separately, once per
            # profile-backed column.
            .select_related("profile")
            .annotate(
                last_session=Max("study_sessions__date"),
                sessions_28d=Count("study_sessions", filter=recent, distinct=True),
                minutes_28d=Sum("study_sessions__duration_minutes", filter=recent),
                # Joining a second multi-valued relation here would multiply
                # every session row by the user's resource count and inflate
                # minutes_28d, so this one count comes from a subquery.
                resource_count=Coalesce(
                    Subquery(
                        LearningResource.objects.filter(user=OuterRef("pk"))
                        .order_by()
                        .values("user")
                        .annotate(total=Count("pk"))
                        .values("total"),
                        output_field=IntegerField(),
                    ),
                    0,
                ),
            )
        )

    @display(
        description="Engagement",
        ordering="last_session",
        label={key: colour for key, (_text, colour) in ENGAGEMENT_BUCKETS.items()},
    )
    def get_engagement(self, obj):
        bucket = engagement_bucket(obj, engagement_cutoffs())
        return bucket, ENGAGEMENT_BUCKETS[bucket][0]

    @admin.display(description="Last session", ordering="last_session")
    def get_last_session(self, obj):
        return obj.last_session or "—"

    @admin.display(description="28d activity", ordering="sessions_28d")
    def get_recent_activity(self, obj):
        if not obj.sessions_28d:
            return "—"
        return f"{obj.sessions_28d} · {round((obj.minutes_28d or 0) / 60)}h"

    @admin.display(description="Resources", ordering="resource_count")
    def get_resource_count(self, obj):
        return obj.resource_count

    @display(
        description="Terms",
        ordering="profile__terms_version",
        label={"current": "success", "outdated": "warning", "never": ""},
    )
    def get_terms_status(self, obj):
        try:
            version = obj.profile.terms_version
        except UserProfile.DoesNotExist:
            version = ""

        if not version:
            return "never", "Never"
        if version == settings.TERMS_VERSION:
            return "current", version
        return "outdated", f"Outdated ({version})"


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


# Models registered by third-party packages keep Django's stock admin classes,
# which render unthemed inside Unfold. Re-registering each one against a
# subclass that also inherits unfold.admin.ModelAdmin themes it while
# inheriting the package's own list_display, filters and readonly fields
# rather than restating them here, where they would drift on upgrade.
for model in (
    AccessAttempt,
    AccessLog,
    AccessFailureLog,
    EmailAddress,
    SocialAccount,
    SocialApp,
    SocialToken,
    Site,
    Group,
):
    stock_admin = type(admin.site._registry[model])
    admin.site.unregister(model)
    admin.site.register(
        model,
        type(f"Unfold{stock_admin.__name__}", (stock_admin, ModelAdmin), {}),
    )
