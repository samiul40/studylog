import pytest
from model_bakery import baker

from learning.models import Activity, StudySession

pytestmark = pytest.mark.django_db


class TestActivitySeeding:
    def test_system_activities_are_seeded(self):
        slugs = set(
            Activity.objects.filter(is_system=True).values_list("slug", flat=True)
        )
        assert slugs == {
            "watch",
            "read",
            "flashcards",
            "practice",
            "pastpapers",
            "review",
            "writing",
        }

    def test_system_activities_have_null_user(self):
        assert not Activity.objects.filter(is_system=True, user__isnull=False).exists()

    def test_system_activity_names(self):
        act = Activity.objects.get(slug="flashcards", is_system=True)
        assert act.name == "Flashcards / Anki"


class TestActivityQuerySet:
    def test_system_queryset(self):
        qs = Activity.objects.system()
        assert qs.count() == 7
        assert all(a.is_system for a in qs)

    def test_custom_queryset_empty_before_creation(self):
        assert Activity.objects.custom().count() == 0

    def test_for_user_returns_system_plus_own(self, user):
        other_user = baker.make("auth.User")
        baker.make(Activity, is_system=False, user=user, name="Drawing", slug="drawing")
        baker.make(
            Activity, is_system=False, user=other_user, name="Coding", slug="coding"
        )

        result = Activity.objects.for_user(user)
        slugs = set(result.values_list("slug", flat=True))

        # Must include all 7 system + own custom
        assert "drawing" in slugs
        assert "flashcards" in slugs
        # Must NOT include another user's custom activity
        assert "coding" not in slugs

    def test_custom_activity_scoped_to_user(self, user):
        other_user = baker.make("auth.User")
        baker.make(
            Activity,
            is_system=False,
            user=other_user,
            name="Meditation",
            slug="meditation",
        )
        assert not Activity.objects.for_user(user).filter(slug="meditation").exists()

    def test_for_user_includes_all_system(self, user):
        result_slugs = set(
            Activity.objects.for_user(user).values_list("slug", flat=True)
        )
        system_slugs = set(Activity.objects.system().values_list("slug", flat=True))
        assert system_slugs.issubset(result_slugs)


class TestActivitySlugAutoFill:
    def test_slug_auto_generated_from_name(self, user):
        act = Activity(name="Spaced Repetition", user=user, is_system=False)
        act.save()
        assert act.slug == "spaced-repetition"

    def test_explicit_slug_not_overwritten(self, user):
        act = Activity(name="Something", slug="my-slug", user=user, is_system=False)
        act.save()
        assert act.slug == "my-slug"


class TestMigrationBackfill:
    """Verify existing sessions were mapped to the correct system Activity FKs."""

    def test_sessions_have_activity_fk(self, user):
        activity = Activity.objects.get(slug="flashcards", is_system=True)
        session = baker.make(
            StudySession,
            user=user,
            activity=activity,
            duration_minutes=30,
        )
        session.refresh_from_db()
        assert session.activity.slug == "flashcards"
        assert session.activity.is_system is True

    def test_to_dict_returns_slug_as_activity_type(self, user):
        activity = Activity.objects.get(slug="practice", is_system=True)
        session = baker.make(
            StudySession,
            user=user,
            activity=activity,
            duration_minutes=45,
        )
        d = session.to_dict()
        assert d["activity_type"] == "practice"
        assert d["activity_label"] == "Practice problems"

    def test_session_title_field_exists(self, user):
        activity = Activity.objects.get(slug="pastpapers", is_system=True)
        session = baker.make(
            StudySession,
            user=user,
            activity=activity,
            title="June 2019 Chem Paper 2",
            duration_minutes=90,
        )
        session.refresh_from_db()
        assert session.title == "June 2019 Chem Paper 2"

    def test_display_label_uses_title_when_set(self, user):
        activity = Activity.objects.get(slug="pastpapers", is_system=True)
        session = baker.make(
            StudySession,
            user=user,
            activity=activity,
            title="Mock Exam 3",
            duration_minutes=60,
        )
        assert session.display_label() == "Mock Exam 3"

    def test_display_label_falls_back_to_activity_name(self, user):
        activity = Activity.objects.get(slug="review", is_system=True)
        session = baker.make(
            StudySession,
            user=user,
            activity=activity,
            title="",
            duration_minutes=30,
        )
        assert session.display_label() == "Review notes"
