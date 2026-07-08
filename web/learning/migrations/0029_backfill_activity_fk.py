from django.db import migrations

# Maps the old activity_type string values to the new system Activity slugs.
SLUG_MAP = {
    "video_watch": "watch",
    "reading": "read",
    "flashcards": "flashcards",
    "practice": "practice",
    "past_papers": "pastpapers",
    "review_notes": "review",
    "writing": "writing",
}


def backfill_activity_fk(apps, schema_editor):
    StudySession = apps.get_model("learning", "StudySession")
    Activity = apps.get_model("learning", "Activity")

    activity_cache = {
        a.slug: a
        for a in Activity.objects.filter(is_system=True)
    }

    sessions = StudySession.objects.filter(activity__isnull=True)
    for session in sessions.iterator(chunk_size=500):
        new_slug = SLUG_MAP.get(session.activity_type)
        if new_slug and new_slug in activity_cache:
            session.activity = activity_cache[new_slug]
            session.save(update_fields=["activity"])


def reverse_backfill(apps, schema_editor):
    # Restore activity_type from the activity slug (reverse slug map).
    reverse_map = {v: k for k, v in SLUG_MAP.items()}
    StudySession = apps.get_model("learning", "StudySession")
    for session in StudySession.objects.exclude(
        activity__isnull=True
    ).select_related("activity").iterator(chunk_size=500):
        slug = session.activity.slug
        old_type = reverse_map.get(slug, slug)
        session.activity_type = old_type
        session.save(update_fields=["activity_type"])


class Migration(migrations.Migration):

    dependencies = [
        ("learning", "0028_studysession_add_activity_fk"),
    ]

    operations = [
        migrations.RunPython(
            backfill_activity_fk, reverse_code=reverse_backfill
        ),
    ]
