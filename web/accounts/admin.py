from datetime import timedelta
from urllib.parse import quote

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialApp, SocialToken
from axes.models import AccessAttempt, AccessFailureLog, AccessLog
from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm
from django.contrib.auth.models import Group
from django.contrib.sites.models import Site
from django.db.models import Count, IntegerField, Max, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import DropdownFilter
from unfold.decorators import display

from learning.models import LearningResource
from learning.services.user_activity import get_user_activity

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


class UserAdminForm(UserChangeForm):
    """Carries the profile's one editable field on the user form itself.

    With it here the page is a single stack of collapsible fieldsets instead
    of a form plus an inline that cannot collapse with the rest.
    """

    timezone = forms.CharField(max_length=64, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profile = profile_of(self.instance)
        if profile:
            self.fields["timezone"].initial = profile.timezone


def profile_of(user):
    """The user's profile, or None — signup creates it, but purges can't."""
    try:
        return user.profile
    except (UserProfile.DoesNotExist, AttributeError):
        return None


def consent_field(name):
    """A read-only accessor for one UserProfile consent field.

    Consent records something the user did, so it is shown and never edited;
    these exist only to reach the profile's values from the user's fieldsets.
    """

    def accessor(self, obj):
        profile = profile_of(obj)
        value = getattr(profile, name, None) if profile else None
        if value is None or value == "":
            return "—"
        return value

    accessor.__name__ = f"consent_{name}"
    accessor.short_description = name.replace("_", " ").capitalize()
    return accessor


CONSENT_DISPLAYS = tuple(f"consent_{name}" for name in CONSENT_FIELDS)


def identity_of(user):
    """The header strip's contents: who this account belongs to."""
    profile = profile_of(user)
    name = user.get_full_name() or user.get_username()
    return {
        "initial": name[:1].upper() or "?",
        "name": name,
        "email": user.email,
        "timezone": profile.timezone if profile else "no profile",
        "joined": date_format(timezone.localtime(user.date_joined), "j M Y"),
    }


def compact_duration(minutes):
    """A duration short enough for a card value: "45m", "3h", "0h"."""
    if minutes and minutes < 60:
        return f"{minutes}m"
    return f"{round((minutes or 0) / 60)}h"


def relative_day(day):
    """How long ago a date was, in words short enough for a card value."""
    delta = (timezone.localdate() - day).days
    if delta <= 0:
        return "Today"
    if delta == 1:
        return "Yesterday"
    return f"{delta}d ago"


def activity_cards(user, activity):
    """The five equal cards under the identity strip."""
    window = activity["window_days"]
    sessions_28d = activity["sessions_28d"]
    last = activity["last_session"]

    if sessions_28d:
        time_detail = (
            f"{compact_duration(activity['minutes_total'])} lifetime · "
            f"{activity['average_minutes']}m avg"
        )
    else:
        # "0h" above a lifetime total reads as a bug rather than a quiet
        # month, so the sub-line says which of the two the zero refers to.
        time_detail = f"none in last {window} days"

    if last:
        context = [last.activity.name]
        if last.resource:
            context.append(last.resource.title)
        last_value = relative_day(last.date)
        last_detail = " · ".join(context)
        last_title = f"{date_format(last.date, 'j M Y')} · {last_detail}"
    else:
        last_value, last_detail, last_title = "—", "never logged", None

    return [
        {
            "label": f"Sessions ({window}d)",
            "value": sessions_28d,
            "detail": f"{activity['sessions_total']} lifetime",
        },
        {
            "label": f"Time ({window}d)",
            "value": compact_duration(activity["minutes_28d"]),
            "detail": time_detail,
        },
        {
            "label": "Current streak",
            "value": f"{activity['current_streak']}d",
            "detail": f"best {activity['best_streak']}d",
        },
        {
            "label": "Resources",
            "value": getattr(user, "resource_count", None) or 0,
            "detail": "owned",
        },
        {
            "label": "Last session",
            "value": last_value,
            "detail": last_detail,
            "title": last_title,
        },
    ]


class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserAdminForm
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

    readonly_fields = (
        "activity_summary",
        "last_login",
        "date_joined",
        "get_deletion_requested_at",
    ) + CONSENT_DISPLAYS

    # The page opens on who this is and what they have done; everything an
    # admin only occasionally needs is one click away rather than in the way.
    fieldsets = (
        # "full-width" drops the label gutter — see templates/admin/includes.
        ("Activity", {"classes": ("full-width",), "fields": ("activity_summary",)}),
        (
            "Account",
            {"fields": ("username", "email", "first_name", "last_name", "password")},
        ),
        (
            "Permissions",
            {
                "classes": ("collapse",),
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (
            "Consent record",
            {"classes": ("collapse",), "fields": CONSENT_DISPLAYS},
        ),
        (
            "Dates & deletion",
            {
                "classes": ("collapse",),
                "fields": (
                    "last_login",
                    "date_joined",
                    "get_deletion_requested_at",
                ),
            },
        ),
    )

    def get_fieldsets(self, request, obj=None):
        # The add form has no user yet, so no activity and no profile.
        if obj is None:
            return self.add_fieldsets
        fieldsets = super().get_fieldsets(request, obj)
        # "timezone" is a form field rather than a model field, so it is added
        # here instead of being listed above where the checks would reject it.
        account = dict(fieldsets[1][1])
        account["fields"] = (*account["fields"], "timezone")
        return (fieldsets[0], (fieldsets[1][0], account), *fieldsets[2:])

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        profile = profile_of(obj)
        if profile and "timezone" in form.cleaned_data:
            profile.timezone = form.cleaned_data["timezone"]
            profile.save(update_fields=["timezone"])

    @admin.display(description="")
    def activity_summary(self, obj):
        activity = get_user_activity(obj)
        bucket = engagement_bucket(obj, engagement_cutoffs())
        text, colour = ENGAGEMENT_BUCKETS[bucket]

        return render_to_string(
            "admin/accounts/user_activity.html",
            {
                "identity": identity_of(obj),
                "engagement": {"text": text, "colour": colour},
                "cards": activity_cards(obj, activity),
                "links": self.drill_downs(obj),
            },
        )

    @staticmethod
    def drill_downs(obj):
        """Pre-filtered changelists for everything this user owns."""
        by_user = [
            ("learning", "studysession", "Study sessions"),
            ("learning", "learningresource", "Learning resources"),
            ("learning", "featurerequest", "Feature requests"),
        ]
        links = [
            {
                "label": label,
                "url": (
                    f"{reverse(f'admin:{app}_{model}_changelist')}"
                    f"?user__id__exact={obj.pk}"
                ),
            }
            for app, model, label in by_user
        ]
        # axes records a username string, not a user FK, so its changelist has
        # nothing to filter on — the search box is the only way in.
        links.append(
            {
                "label": "Access attempts",
                "url": (
                    f"{reverse('admin:axes_accessattempt_changelist')}"
                    f"?q={quote(obj.get_username())}"
                ),
            }
        )
        return links

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

    @admin.display(description="Deletion requested")
    def get_deletion_requested_at(self, obj):
        profile = profile_of(obj)
        return (profile.deletion_requested_at if profile else None) or "—"


# Eight near-identical read-only accessors, one per consent field. Written as
# a loop because spelling them out would be eight copies of the same body.
for _name in CONSENT_FIELDS:
    setattr(UserAdmin, f"consent_{_name}", consent_field(_name))


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
