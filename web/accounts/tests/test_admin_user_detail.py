import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from model_bakery import baker

from accounts.admin import CONSENT_DISPLAYS
from accounts.models import UserProfile
from learning.models import Activity, FeatureRequest, LearningResource, StudySession

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


def detail_url(user):
    return reverse("admin:auth_user_change", args=[user.pk])


def make_session(user, offset, minutes=30, **kwargs):
    kwargs.setdefault(
        "activity", Activity.objects.get(slug="flashcards", is_system=True)
    )
    return baker.make(
        StudySession,
        user=user,
        date=TODAY - datetime.timedelta(days=offset),
        duration_minutes=minutes,
        status=StudySession.Status.LOGGED,
        **kwargs,
    )


def fieldset_names(response):
    return [name for name, _opts in response.context["adminform"].fieldsets]


def collapsed_fieldsets(response):
    return [
        name
        for name, opts in response.context["adminform"].fieldsets
        if "collapse" in opts.get("classes", ())
    ]


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


def test_the_fieldsets_are_in_the_intended_order(client_logged_in, user):
    response = client_logged_in.get(detail_url(user))

    assert fieldset_names(response) == [
        "Activity",
        "Account",
        "Permissions",
        "Consent record",
        "Dates & deletion",
    ]


def test_only_activity_and_account_open(client_logged_in, user):
    """The page should open on identity plus activity, nothing else."""
    response = client_logged_in.get(detail_url(user))

    assert collapsed_fieldsets(response) == [
        "Permissions",
        "Consent record",
        "Dates & deletion",
    ]


def test_the_account_fieldset_carries_the_profile_timezone(client_logged_in, user):
    response = client_logged_in.get(detail_url(user))

    account = dict(response.context["adminform"].fieldsets)["Account"]

    assert "timezone" in account["fields"]


def test_the_consent_fieldset_holds_all_eight_fields(client_logged_in, user):
    response = client_logged_in.get(detail_url(user))

    consent = dict(response.context["adminform"].fieldsets)["Consent record"]

    assert consent["fields"] == CONSENT_DISPLAYS
    assert len(CONSENT_DISPLAYS) == 8


def test_the_profile_inline_is_gone(client_logged_in, user):
    response = client_logged_in.get(detail_url(user))

    assert response.context["inline_admin_formsets"] == []


# ---------------------------------------------------------------------------
# Activity block
# ---------------------------------------------------------------------------


def test_the_activity_block_reports_the_session_record(client_logged_in, user):
    resource = baker.make(LearningResource, user=user, title="Linear Algebra")
    make_session(user, 0, minutes=60, resource=resource)
    make_session(user, 1, minutes=60)

    content = client_logged_in.get(detail_url(user)).content.decode()

    assert "Sessions (28d)" in content
    assert "Current streak" in content
    assert "2d" in content  # a two-day streak
    assert "Linear Algebra" in content  # the last session's resource


def test_the_block_is_five_cards_in_one_row(client_logged_in, user):
    content = client_logged_in.get(detail_url(user)).content.decode()

    for label in (
        "Sessions (28d)",
        "Time (28d)",
        "Current streak",
        "Resources",
        "Last session",
    ):
        assert label in content
    assert "lg:grid-cols-5" in content


def test_the_activity_fieldset_spans_the_full_width(client_logged_in, user):
    """Inside a normal form row the cards sit behind an empty label gutter."""
    response = client_logged_in.get(detail_url(user))
    content = response.content.decode()

    activity = dict(response.context["adminform"].fieldsets)["Activity"]

    assert "full-width" in activity["classes"]
    # The escape hatch skips the label column entirely.
    assert 'for="id_activity_summary"' not in content


def test_the_identity_strip_carries_who_this_is(client_logged_in, user):
    user.first_name = "Ada"
    user.last_name = "Lovelace"
    user.email = "ada@example.com"
    user.save()
    user.profile.timezone = "Europe/London"
    user.profile.save()

    content = client_logged_in.get(detail_url(user)).content.decode()

    assert "Ada Lovelace" in content
    assert "ada@example.com" in content
    assert "Europe/London" in content
    assert "joined" in content


def test_the_identity_strip_shows_the_engagement_tag(client_logged_in, user):
    for offset in (0, 1, 2):
        make_session(user, offset)

    content = client_logged_in.get(detail_url(user)).content.decode()

    assert "Active" in content


def test_a_user_with_no_sessions_says_so(client_logged_in, user):
    content = client_logged_in.get(detail_url(user)).content.decode()

    assert "never logged" in content


def test_a_quiet_month_does_not_read_as_a_broken_card(client_logged_in, user):
    """0h beside a lifetime total looks like a bug, so say what the zero is."""
    make_session(user, 200, minutes=660)

    content = client_logged_in.get(detail_url(user)).content.decode()

    assert "none in last 28 days" in content
    assert "11h lifetime" not in content


def test_a_busy_month_keeps_the_lifetime_qualifier(client_logged_in, user):
    make_session(user, 1, minutes=120)
    make_session(user, 200, minutes=540)

    content = client_logged_in.get(detail_url(user)).content.decode()

    assert "11h lifetime" in content
    assert "none in last 28 days" not in content


def test_under_an_hour_is_shown_in_minutes(client_logged_in, user):
    """Rounding 45 minutes down to "0h" would look like nothing happened."""
    make_session(user, 1, minutes=45)

    content = client_logged_in.get(detail_url(user)).content.decode()

    assert "45m" in content


def test_the_drill_down_links_are_pre_filtered(client_logged_in, user):
    content = client_logged_in.get(detail_url(user)).content.decode()

    for model in ("studysession", "learningresource", "featurerequest"):
        url = reverse(f"admin:learning_{model}_changelist")
        assert f"{url}?user__id__exact={user.pk}" in content

    assert reverse("admin:axes_accessattempt_changelist") in content


@pytest.mark.parametrize(
    "model", ["studysession", "learningresource", "featurerequest"]
)
def test_the_drill_down_filters_are_accepted_by_the_changelist(
    client_logged_in, user, model
):
    """A rejected lookup would 500 rather than fail quietly."""
    other = baker.make("auth.User", username="stranger")
    activity = Activity.objects.get(slug="flashcards", is_system=True)
    baker.make(LearningResource, user=user)
    baker.make(LearningResource, user=other)
    baker.make(FeatureRequest, user=user, idea="mine")
    baker.make(FeatureRequest, user=other, idea="theirs")
    for owner in (user, other):
        baker.make(
            StudySession,
            user=owner,
            date=TODAY,
            activity=activity,
            duration_minutes=30,
        )

    url = reverse(f"admin:learning_{model}_changelist")
    response = client_logged_in.get(url, {"user__id__exact": user.pk})

    assert response.status_code == 200
    assert {row.user_id for row in response.context["cl"].queryset} == {user.pk}


# ---------------------------------------------------------------------------
# Editing
# ---------------------------------------------------------------------------


def test_the_timezone_saves_back_to_the_profile(client_logged_in, user):
    response = client_logged_in.post(
        detail_url(user),
        {
            "username": user.username,
            "email": user.email,
            "first_name": "",
            "last_name": "",
            "timezone": "Europe/London",
            "is_active": "on",
            "last_login_0": "",
            "last_login_1": "",
            "date_joined_0": user.date_joined.strftime("%Y-%m-%d"),
            "date_joined_1": user.date_joined.strftime("%H:%M:%S"),
        },
    )
    user.profile.refresh_from_db()

    assert response.status_code == 302
    assert user.profile.timezone == "Europe/London"


def test_a_user_with_no_profile_still_opens(client_logged_in):
    """Purges can leave a user without a profile; the page must survive it."""
    orphan = baker.make("auth.User", username="orphan")
    UserProfile.objects.filter(user=orphan).delete()

    response = client_logged_in.get(detail_url(orphan))

    assert response.status_code == 200


def test_the_add_form_still_works(client_logged_in):
    response = client_logged_in.get(reverse("admin:auth_user_add"))

    assert response.status_code == 200
    assert fieldset_names(response) == [None]


def test_a_user_can_still_be_created(client_logged_in):
    response = client_logged_in.post(
        reverse("admin:auth_user_add"),
        {
            "username": "brandnew",
            "password1": "a-long-enough-password",
            "password2": "a-long-enough-password",
        },
    )

    assert response.status_code == 302
    assert UserProfile.objects.filter(user__username="brandnew").exists()
