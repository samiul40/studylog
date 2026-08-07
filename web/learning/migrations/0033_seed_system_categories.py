from django.db import migrations

SYSTEM_CATEGORIES = [
    ("science", "Science"),
    ("technology", "Technology"),
    ("mathematics", "Mathematics"),
    ("humanities", "Humanities"),
]


def seed_system_categories(apps, schema_editor):
    Category = apps.get_model("learning", "Category")
    for slug, name in SYSTEM_CATEGORIES:
        Category.objects.get_or_create(
            slug=slug,
            is_system=True,
            defaults={"name": name, "user": None},
        )


def unseed_system_categories(apps, schema_editor):
    Category = apps.get_model("learning", "Category")
    Category.objects.filter(
        is_system=True,
        slug__in=[slug for slug, _ in SYSTEM_CATEGORIES],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("learning", "0032_category_learningresource_category_and_more"),
    ]

    operations = [
        migrations.RunPython(
            seed_system_categories,
            reverse_code=unseed_system_categories,
        ),
    ]
