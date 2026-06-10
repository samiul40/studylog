import json

import pytest
from django.urls import reverse
from model_bakery import baker

from learning.models import LearningResource, LearningUnit

pytestmark = pytest.mark.django_db


def test_learning_unit_create(client_logged_in, user):
    resource = baker.make(LearningResource, user=user)

    url = reverse(
        "learning:unit_create",
        kwargs={"resource_pk": resource.pk},
    )

    data = {
        "title": "Unit 1",
        "description": "Test unit",
        "order": 1,
    }

    response = client_logged_in.post(url, data)

    assert response.status_code == 302
    assert LearningUnit.objects.filter(
        resource=resource,
        title="Unit 1",
    ).exists()


def test_learning_unit_update(client_logged_in, user):
    resource = baker.make(LearningResource, user=user)
    unit = baker.make(LearningUnit, resource=resource, title="Old Title")

    url = reverse(
        "learning:unit_update",
        kwargs={"resource_pk": resource.pk, "unit_pk": unit.pk},
    )

    data = {
        "title": "Updated Title",
        "description": "",
        "order": unit.order,
    }

    response = client_logged_in.post(url, data)

    unit.refresh_from_db()

    assert response.status_code == 302
    assert unit.title == "Updated Title"


def test_learning_unit_delete_reorders_units(client_logged_in, user):
    resource = baker.make(LearningResource, user=user)

    _ = baker.make(LearningUnit, resource=resource, order=1)
    unit2 = baker.make(LearningUnit, resource=resource, order=2)
    _ = baker.make(LearningUnit, resource=resource, order=3)

    url = reverse(
        "learning:unit_delete",
        kwargs={"resource_pk": resource.pk, "unit_pk": unit2.pk},
    )

    response = client_logged_in.post(url)

    assert response.status_code == 302

    remaining_units = LearningUnit.objects.filter(resource=resource).order_by("order")

    assert list(remaining_units.values_list("order", flat=True)) == [1, 2]


def test_user_cannot_modify_units_of_other_users_resource(client_logged_in):
    other_resource = baker.make(LearningResource)
    unit = baker.make(LearningUnit, resource=other_resource)

    url = reverse(
        "learning:unit_update",
        kwargs={"resource_pk": other_resource.pk, "unit_pk": unit.pk},
    )

    response = client_logged_in.post(url, {"title": "Hack"})

    assert response.status_code == 404


def test_learning_unit_reorder(client_logged_in, user):
    resource = baker.make(LearningResource, user=user)

    unit1 = baker.make(LearningUnit, resource=resource, order=1)
    unit2 = baker.make(LearningUnit, resource=resource, order=2)

    url = reverse(
        "learning:unit_reorder",
        kwargs={"resource_pk": resource.pk},
    )

    payload = {
        "order": [
            {"id": unit1.id, "order": 2},
            {"id": unit2.id, "order": 1},
        ]
    }

    response = client_logged_in.post(
        url,
        data=json.dumps(payload),
        content_type="application/json",
    )

    unit1.refresh_from_db()
    unit2.refresh_from_db()

    assert response.status_code == 200
    assert unit1.order == 2
    assert unit2.order == 1


@pytest.mark.parametrize(
    "url",
    [
        lambda resource: reverse(
            "learning:unit_create", kwargs={"resource_pk": resource.pk}
        ),
        lambda resource: reverse(
            "learning:unit_update", kwargs={"resource_pk": resource.pk, "unit_pk": 1}
        ),
        lambda resource: reverse(
            "learning:unit_delete", kwargs={"resource_pk": resource.pk, "unit_pk": 1}
        ),
        lambda resource: reverse(
            "learning:unit_reorder", kwargs={"resource_pk": resource.pk}
        ),
        lambda resource: reverse("learning:unit_update_status", kwargs={"pk": 1}),
    ],
)
def test_learning_unit_views_require_login(client, url):
    resource = baker.make(LearningResource)

    response = client.get(url(resource))

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.parametrize("new_status", ["not_started", "in_progress", "completed"])
def test_learning_unit_update_status_all_options(client_logged_in, user, new_status):
    resource = baker.make(LearningResource, user=user)
    unit = baker.make(
        LearningUnit,
        resource=resource,
        status="not_started",
    )

    url = reverse("learning:unit_update_status", kwargs={"pk": unit.pk})

    response = client_logged_in.post(url, {"status": new_status})

    unit.refresh_from_db()

    assert response.status_code == 302
    assert unit.status == new_status


def test_learning_unit_update_status_invalid_value(client_logged_in, user):
    resource = baker.make(LearningResource, user=user)
    unit = baker.make(LearningUnit, resource=resource, status="not_started")

    url = reverse("learning:unit_update_status", kwargs={"pk": unit.pk})

    response = client_logged_in.post(url, {"status": "invalid_status"})

    unit.refresh_from_db()

    assert response.status_code == 302
    assert unit.status == "not_started"


def test_user_cannot_update_other_users_unit_status(client_logged_in):
    other_resource = baker.make(LearningResource)
    unit = baker.make(LearningUnit, resource=other_resource)

    url = reverse("learning:unit_update_status", kwargs={"pk": unit.pk})

    response = client_logged_in.post(url, {"status": "completed"})

    assert response.status_code == 404


def test_learning_unit_create_invalid_form(client_logged_in, user):
    resource = baker.make(LearningResource, user=user)

    url = reverse(
        "learning:unit_create",
        kwargs={"resource_pk": resource.pk},
    )

    data = {
        "title": "",
        "description": "Some description",
        "order": 1,
    }

    response = client_logged_in.post(url, data, follow=True)

    assert not LearningUnit.objects.filter(resource=resource).exists()
    assert response.status_code == 200

    messages = list(response.context["messages"])
    assert any("Invalid input" in str(m) for m in messages)
