from django.apps import apps as django_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations


def add_session_permissions(apps, schema_editor):
    # Permissions are normally created by post_migrate, which runs after all
    # migrations complete. Force-create them now so we can assign them here.
    create_permissions(django_apps.get_app_config("learning"), verbosity=0)

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    group, _ = Group.objects.get_or_create(name="Learning User")
    perms = Permission.objects.filter(
        content_type__app_label="learning",
        codename__in=[
            "add_studysession",
            "change_studysession",
            "delete_studysession",
            "view_studysession",
        ],
    )
    # .add() instead of .set() — preserves the existing group permissions
    group.permissions.add(*perms)


class Migration(migrations.Migration):

    dependencies = [
        ("learning", "0021_add_study_session"),
    ]

    operations = [
        migrations.RunPython(add_session_permissions, migrations.RunPython.noop),
    ]
