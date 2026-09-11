import pytest
from django.urls import reverse
from model_bakery import baker

from learning.models import FeatureRequest

pytestmark = pytest.mark.django_db


def test_changelist_loads(client_logged_in, user):
    baker.make(FeatureRequest, user=user, idea="Add a streak counter")

    response = client_logged_in.get(reverse("admin:learning_featurerequest_changelist"))

    assert response.status_code == 200
    assert "Add a streak counter" in response.content.decode()


def test_changelist_truncates_long_ideas(client_logged_in, user):
    baker.make(FeatureRequest, user=user, idea="x" * 2000)

    response = client_logged_in.get(reverse("admin:learning_featurerequest_changelist"))

    assert response.status_code == 200
    assert "x" * 2000 not in response.content.decode()


def test_change_page_loads(client_logged_in, user):
    request = baker.make(FeatureRequest, user=user, idea="Add dark mode")

    response = client_logged_in.get(
        reverse("admin:learning_featurerequest_change", args=[request.pk])
    )

    assert response.status_code == 200


def test_status_is_editable_from_the_changelist(client_logged_in, user):
    request = baker.make(FeatureRequest, user=user, idea="Ship this please")
    url = reverse("admin:learning_featurerequest_changelist")

    response = client_logged_in.post(
        url,
        {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-id": str(request.pk),
            "form-0-status": FeatureRequest.StatusChoices.SHIPPED,
            "_save": "Save",
        },
    )

    assert response.status_code == 302

    request.refresh_from_db()
    assert request.status == FeatureRequest.StatusChoices.SHIPPED


def test_ideas_cannot_be_created_from_the_admin(client_logged_in):
    response = client_logged_in.get(reverse("admin:learning_featurerequest_add"))

    assert response.status_code == 403
