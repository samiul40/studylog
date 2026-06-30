from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    timezone = models.CharField(max_length=64, default="UTC")
    deletion_requested_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user} profile"
