from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    timezone = models.CharField(max_length=64, default="UTC")
    deletion_requested_at = models.DateTimeField(null=True, blank=True)

    terms_accepted = models.BooleanField(default=False)
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    terms_version = models.CharField(max_length=20, blank=True, default="")

    privacy_accepted = models.BooleanField(default=False)
    privacy_accepted_at = models.DateTimeField(null=True, blank=True)
    privacy_version = models.CharField(max_length=20, blank=True, default="")

    age_confirmed = models.BooleanField(default=False)
    age_confirmed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user} profile"
