import pytest
from model_bakery import baker

from learning.models import FeatureRequest

pytestmark = pytest.mark.django_db


def test_feature_request_str(user):
    request = baker.make(FeatureRequest, user=user, idea="Add a streak counter")

    assert str(request) == f"Add a streak counter - {user.username}"


def test_feature_request_defaults_to_new_status(user):
    request = baker.make(FeatureRequest, user=user, idea="Add dark mode toggle")

    assert request.status == FeatureRequest.StatusChoices.NEW


def test_feature_request_survives_user_deletion(user):
    request = baker.make(FeatureRequest, user=user, idea="Keep this suggestion")

    user.delete()
    request.refresh_from_db()

    assert request.user is None
    assert request.idea == "Keep this suggestion"


def test_feature_request_str_handles_deleted_user(user):
    request = baker.make(FeatureRequest, user=user, idea="Orphaned idea")

    user.delete()
    request.refresh_from_db()

    assert str(request) == "Orphaned idea - deleted user"
