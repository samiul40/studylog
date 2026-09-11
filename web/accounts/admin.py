from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db.models import Q

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


class TermsStatusFilter(admin.SimpleListFilter):
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


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    extra = 0
    # Consent is a record of something the user did. Editing it here would be
    # fabricating that record, so the whole block is read-only.
    readonly_fields = ("deletion_requested_at",) + CONSENT_FIELDS
    fields = ("timezone", "deletion_requested_at") + CONSENT_FIELDS


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_active",
        "get_terms_status",
        "get_deletion_requested_at",
    )
    list_filter = BaseUserAdmin.list_filter + (
        TermsStatusFilter,
        "profile__deletion_requested_at",
    )

    ordering = ("-date_joined",)

    def get_queryset(self, request):
        # Without this each row fetches its profile separately, once per
        # profile-backed column.
        return super().get_queryset(request).select_related("profile")

    @admin.display(description="Terms", ordering="profile__terms_version")
    def get_terms_status(self, obj):
        try:
            version = obj.profile.terms_version
        except UserProfile.DoesNotExist:
            version = ""

        if not version:
            return "— Never"
        if version == settings.TERMS_VERSION:
            return f"✓ {version}"
        return f"Outdated ({version})"

    @admin.display(
        description="Deletion requested",
        ordering="profile__deletion_requested_at",
    )
    def get_deletion_requested_at(self, obj):
        try:
            return obj.profile.deletion_requested_at or "—"
        except UserProfile.DoesNotExist:
            return "—"


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
