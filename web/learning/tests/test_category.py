import pytest
from django.db import IntegrityError
from django.urls import reverse
from model_bakery import baker

from learning.forms import LearningResourceForm
from learning.models import Category, LearningResource

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Uniqueness constraints
# ---------------------------------------------------------------------------


def test_two_users_can_create_custom_categories_with_same_slug():
    user_a = baker.make("auth.User")
    user_b = baker.make("auth.User")
    Category.objects.create(name="Chemistry", slug="chemistry", user=user_a)
    # Should not raise — different users, same slug is allowed for custom categories
    Category.objects.create(name="Chemistry", slug="chemistry", user=user_b)


def test_same_user_cannot_create_duplicate_custom_category_slug():
    user = baker.make("auth.User")
    Category.objects.create(name="Chemistry", slug="chemistry", user=user)
    with pytest.raises(IntegrityError):
        Category.objects.create(name="Chemistry Alt", slug="chemistry", user=user)


def test_system_category_slug_is_globally_unique():
    Category.objects.create(name="Unique System", slug="unique-system", is_system=True)
    with pytest.raises(IntegrityError):
        Category.objects.create(
            name="Unique System Dup", slug="unique-system", is_system=True
        )


def test_seeded_system_categories_exist():
    slugs = set(Category.objects.filter(is_system=True).values_list("slug", flat=True))
    assert {"science", "technology", "mathematics", "humanities"} <= slugs


def test_slug_auto_generated_from_name():
    user = baker.make("auth.User")
    category = Category.objects.create(name="Music Theory", user=user)
    assert category.slug == "music-theory"


# ---------------------------------------------------------------------------
# Form queryset isolation
# ---------------------------------------------------------------------------


def test_form_queryset_excludes_other_users_custom_categories():
    owner = baker.make("auth.User")
    other = baker.make("auth.User")
    other_category = baker.make(Category, is_system=False, user=other)

    form = LearningResourceForm(user=owner)

    assert other_category not in form.fields["category"].queryset


def test_form_queryset_includes_own_custom_categories():
    user = baker.make("auth.User")
    own_category = baker.make(Category, is_system=False, user=user)

    form = LearningResourceForm(user=user)

    assert own_category in form.fields["category"].queryset


def test_form_queryset_includes_system_categories():
    user = baker.make("auth.User")
    system_category = Category.objects.filter(is_system=True).first()

    form = LearningResourceForm(user=user)

    assert system_category in form.fields["category"].queryset


# ---------------------------------------------------------------------------
# View: creating a resource with a new category assigns user ownership
# ---------------------------------------------------------------------------


def test_resource_create_new_category_is_owned_by_creating_user(client_logged_in, user):
    data = {
        "title": "My Chemistry Resource",
        "new_resource_type": "My Custom Type",
        "new_content_kind": "video",
        "new_category": "Chemistry",
        "description": "",
    }

    response = client_logged_in.post(reverse("learning:resource_create"), data)

    assert response.status_code == 302
    category = Category.objects.get(slug="chemistry")
    assert category.user == user
    assert category.is_system is False


def test_resource_create_new_category_not_visible_to_other_user(client_logged_in, user):
    data = {
        "title": "My Chemistry Resource",
        "new_resource_type": "My Custom Type",
        "new_content_kind": "video",
        "new_category": "Private Category",
        "description": "",
    }
    client_logged_in.post(reverse("learning:resource_create"), data)

    other = baker.make("auth.User")
    form = LearningResourceForm(user=other)

    private_category = Category.objects.get(slug="private-category")
    assert private_category not in form.fields["category"].queryset


def test_resource_create_without_category_leaves_it_unset(client_logged_in, user):
    data = {
        "title": "Uncategorized Resource",
        "new_resource_type": "Another Type",
        "new_content_kind": "video",
        "description": "",
    }

    client_logged_in.post(reverse("learning:resource_create"), data)

    resource = LearningResource.objects.get(title="Uncategorized Resource")
    assert resource.category is None
