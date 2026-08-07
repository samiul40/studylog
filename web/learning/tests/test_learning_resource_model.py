import pytest
from django.urls import reverse
from model_bakery import baker

from learning.models import Category, LearningResource

pytestmark = pytest.mark.django_db


def test_learning_resource_str(user):
    resource = baker.make(
        LearningResource,
        user=user,
        title="Django Course",
    )

    result = str(resource)

    assert result == f"Django Course - {user.username}"


def test_learning_resource_get_absolute_url(user):
    resource = baker.make(LearningResource, user=user)

    url = resource.get_absolute_url()

    expected_url = reverse(
        "learning:resource_detail",
        kwargs={"pk": resource.pk},
    )

    assert url == expected_url


def test_learning_resource_category_defaults_to_none(user):
    resource = baker.make(LearningResource, user=user, category=None)

    assert resource.category is None


def test_deleting_category_sets_resource_category_to_none(user):
    category = baker.make(Category, is_system=False, user=user)
    resource = baker.make(LearningResource, user=user, category=category)

    category.delete()
    resource.refresh_from_db()

    assert resource.category is None
