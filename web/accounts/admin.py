from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import UserProfile

User = get_user_model()


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    extra = 0
    readonly_fields = ("deletion_requested_at",)
    fields = ("timezone", "deletion_requested_at")


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_active",
        "get_deletion_requested_at",
    )
    list_filter = BaseUserAdmin.list_filter + ("profile__deletion_requested_at",)

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
