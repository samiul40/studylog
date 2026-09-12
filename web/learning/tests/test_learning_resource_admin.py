import pytest
from django.urls import reverse
from model_bakery import baker

from learning.models import LearningResource, LearningUnit

pytestmark = pytest.mark.django_db


def change_url(resource):
    return reverse("admin:learning_learningresource_change", args=[resource.pk])


def test_the_unit_inline_is_drag_sortable(client_logged_in, user):
    """Unfold draws the drag handle from ordering_field, not adminsortable2."""
    resource = baker.make(LearningResource, user=user)
    baker.make(LearningUnit, resource=resource, order=1)

    html = client_logged_in.get(change_url(resource)).content.decode()

    assert 'data-ordering-field="order"' in html
    assert "x-sort" in html
    assert "unfold/js/alpine/alpine.sort" in html
    assert "adminsortable2" not in html


def test_dragging_a_unit_saves_its_new_position(client_logged_in, user):
    """A drag only rewrites the order inputs, so the save path is the formset."""
    resource = baker.make(LearningResource, user=user, title="Algebra")
    first = baker.make(LearningUnit, resource=resource, title="One", order=1)
    second = baker.make(LearningUnit, resource=resource, title="Two", order=2)

    response = client_logged_in.post(
        change_url(resource),
        {
            "user": user.pk,
            "title": "Algebra",
            "resource_type": resource.resource_type_id,
            "category": "",
            "description": "",
            "units-TOTAL_FORMS": "2",
            "units-INITIAL_FORMS": "2",
            "units-MIN_NUM_FORMS": "0",
            "units-MAX_NUM_FORMS": "1000",
            "units-0-id": first.pk,
            "units-0-resource": resource.pk,
            "units-0-order": "2",
            "units-0-title": "One",
            "units-0-status": "not_started",
            "units-1-id": second.pk,
            "units-1-resource": resource.pk,
            "units-1-order": "1",
            "units-1-title": "Two",
            "units-1-status": "not_started",
            "_continue": "Save and continue editing",
        },
    )
    first.refresh_from_db()
    second.refresh_from_db()

    assert response.status_code == 302
    assert first.order == 2
    assert second.order == 1
