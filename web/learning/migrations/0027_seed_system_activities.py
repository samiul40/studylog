from django.db import migrations

SYSTEM_ACTIVITIES = [
    ("watch", "Watched"),
    ("read", "Read"),
    ("flashcards", "Flashcards / Anki"),
    ("practice", "Practice problems"),
    ("pastpapers", "Past papers"),
    ("review", "Review notes"),
    ("writing", "Writing / essays"),
]


def seed_system_activities(apps, schema_editor):
    Activity = apps.get_model("learning", "Activity")
    for slug, name in SYSTEM_ACTIVITIES:
        Activity.objects.get_or_create(
            slug=slug,
            is_system=True,
            defaults={"name": name, "user": None},
        )


def unseed_system_activities(apps, schema_editor):
    Activity = apps.get_model("learning", "Activity")
    Activity.objects.filter(
        is_system=True,
        slug__in=[slug for slug, _ in SYSTEM_ACTIVITIES],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("learning", "0026_create_activity"),
    ]

    operations = [
        migrations.RunPython(
            seed_system_activities,
            reverse_code=unseed_system_activities,
        ),
    ]
