from django.db import migrations

SYSTEM_TYPES = [
    {"name": "Coursera", "slug": "coursera", "content_kind": "video"},
    {"name": "Skillshare", "slug": "skillshare", "content_kind": "video"},
    {
        "name": "LinkedIn Learning",
        "slug": "linkedin-learning",
        "content_kind": "video",
    },
]


def seed_types(apps, schema_editor):
    ResourceType = apps.get_model("learning", "ResourceType")
    for data in SYSTEM_TYPES:
        ResourceType.objects.get_or_create(
            slug=data["slug"],
            defaults={
                "name": data["name"],
                "content_kind": data["content_kind"],
                "is_system": True,
            },
        )


def reverse_seed_types(apps, schema_editor):
    ResourceType = apps.get_model("learning", "ResourceType")
    ResourceType.objects.filter(
        slug__in=[data["slug"] for data in SYSTEM_TYPES], is_system=True
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("learning", "0019_backfill_completed_at"),
    ]

    operations = [
        migrations.RunPython(seed_types, reverse_seed_types),
    ]
