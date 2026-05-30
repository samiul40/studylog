from django.contrib.auth.management import create_permissions
from django.apps import apps as django_apps
from django.db import migrations


def seed_learning_user_group(apps, schema_editor):
    # Permissions are normally created by post_migrate, which runs after all
    # migrations complete. Force-create them now so we can assign them here.
    create_permissions(django_apps.get_app_config("learning"), verbosity=0)

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    group, _ = Group.objects.get_or_create(name="Learning User")
    permissions = Permission.objects.filter(
        content_type__app_label="learning",
        codename__in=[
            "view_learningresource",
            "add_learningresource",
            "change_learningresource",
            "delete_learningresource",
            "view_learningunit",
            "add_learningunit",
            "change_learningunit",
            "delete_learningunit",
            "view_dashboard",
        ],
    )
    group.permissions.set(permissions)


class Migration(migrations.Migration):

    dependencies = [
        ("learning", "0014_add_is_archived_to_learning_resource"),
    ]

    operations = [
        migrations.RunPython(seed_learning_user_group, migrations.RunPython.noop),
    ]
