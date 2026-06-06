import pytest
from django.db import IntegrityError
from django.urls import reverse
from model_bakery import baker

from learning.forms import LearningResourceForm
from learning.models import ResourceType

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Uniqueness constraints
# ---------------------------------------------------------------------------


def test_two_users_can_create_custom_types_with_same_slug():
    user_a = baker.make("auth.User")
    user_b = baker.make("auth.User")
    ResourceType.objects.create(name="Podcast", slug="podcast", user=user_a)
    # Should not raise — different users, same slug is allowed for custom types
    ResourceType.objects.create(name="Podcast", slug="podcast", user=user_b)


def test_same_user_cannot_create_duplicate_custom_type_slug():
    user = baker.make("auth.User")
    ResourceType.objects.create(name="Podcast", slug="podcast", user=user)
    with pytest.raises(IntegrityError):
        ResourceType.objects.create(name="Podcast Alt", slug="podcast", user=user)


def test_system_type_slug_is_globally_unique():
    ResourceType.objects.create(
        name="Unique System", slug="unique-system", is_system=True
    )
    with pytest.raises(IntegrityError):
        ResourceType.objects.create(
            name="Unique System Dup", slug="unique-system", is_system=True
        )


# ---------------------------------------------------------------------------
# Form queryset isolation
# ---------------------------------------------------------------------------


def test_form_queryset_excludes_other_users_custom_types():
    owner = baker.make("auth.User")
    other = baker.make("auth.User")
    other_type = baker.make(ResourceType, is_system=False, user=other)

    form = LearningResourceForm(user=owner)

    assert other_type not in form.fields["resource_type"].queryset


def test_form_queryset_includes_own_custom_types():
    user = baker.make("auth.User")
    own_type = baker.make(ResourceType, is_system=False, user=user)

    form = LearningResourceForm(user=user)

    assert own_type in form.fields["resource_type"].queryset


def test_form_queryset_includes_system_types():
    user = baker.make("auth.User")
    system_type = ResourceType.objects.filter(is_system=True).first()

    form = LearningResourceForm(user=user)

    assert system_type in form.fields["resource_type"].queryset


# ---------------------------------------------------------------------------
# View: resource list context
# ---------------------------------------------------------------------------


def test_resource_list_context_excludes_other_users_custom_types(
    client_logged_in, user
):
    other = baker.make("auth.User")
    other_type = baker.make(ResourceType, is_system=False, user=other)

    response = client_logged_in.get(reverse("learning:resource_list"))

    assert other_type not in response.context["resource_types"]


def test_resource_list_context_includes_own_custom_types(client_logged_in, user):
    own_type = baker.make(ResourceType, is_system=False, user=user)

    response = client_logged_in.get(reverse("learning:resource_list"))

    assert own_type in response.context["resource_types"]


def test_resource_list_context_includes_system_types(client_logged_in):
    system_type = ResourceType.objects.filter(is_system=True).first()

    response = client_logged_in.get(reverse("learning:resource_list"))

    assert system_type in response.context["resource_types"]


# ---------------------------------------------------------------------------
# View: creating a resource with a new type assigns user ownership
# ---------------------------------------------------------------------------


def test_resource_create_new_type_is_owned_by_creating_user(client_logged_in, user):
    data = {
        "title": "My Podcast Resource",
        "new_resource_type": "My Custom Type",
        "new_content_kind": "video",
        "description": "",
    }

    response = client_logged_in.post(reverse("learning:resource_create"), data)

    assert response.status_code == 302
    rt = ResourceType.objects.get(slug="my-custom-type")
    assert rt.user == user
    assert rt.is_system is False


def test_resource_create_new_type_not_visible_to_other_user(client_logged_in, user):
    data = {
        "title": "My Podcast Resource",
        "new_resource_type": "Private Custom Type",
        "new_content_kind": "video",
        "description": "",
    }
    client_logged_in.post(reverse("learning:resource_create"), data)

    other = baker.make("auth.User")
    form = LearningResourceForm(user=other)

    private_type = ResourceType.objects.get(slug="private-custom-type")
    assert private_type not in form.fields["resource_type"].queryset
