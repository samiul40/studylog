from django.db import migrations
from django.db.models import F


def backfill_completed_at(apps, schema_editor):
    """Set completed_at = updated_at for units completed before this field."""
    LearningUnit = apps.get_model("learning", "LearningUnit")
    LearningUnit.objects.filter(
        status="completed",
        completed_at__isnull=True,
    ).update(completed_at=F("updated_at"))


class Migration(migrations.Migration):

    dependencies = [
        ("learning", "0018_learningresource_lr_user_archived_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_completed_at, migrations.RunPython.noop),
    ]
