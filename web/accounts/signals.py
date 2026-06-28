from allauth.account.signals import user_signed_up
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import UserProfile

User = get_user_model()


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(user_signed_up)
def assign_learning_group(sender, request, user, **kwargs):
    group, _ = Group.objects.get_or_create(name="Learning User")
    user.groups.add(group)
