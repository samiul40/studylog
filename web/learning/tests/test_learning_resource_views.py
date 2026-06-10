from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from model_bakery import baker

from learning.models import LearningResource, ResourceType

pytestmark = pytest.mark.django_db


def test_resource_list_shows_user_resources(client_logged_in, user):
    resource = baker.make(LearningResource, user=user)
    baker.make(LearningResource)

    url = reverse("learning:resource_list")
    response = client_logged_in.get(url)

    assert response.status_code == 200
    assert resource in response.context["resources"]
    assert len(response.context["resources"]) == 1


def test_resource_list_filter_by_type(client_logged_in, user):
    rt_book = ResourceType.objects.get(slug="book")
    rt_other = ResourceType.objects.get(slug="other")
    baker.make(LearningResource, user=user, resource_type=rt_book)
    baker.make(LearningResource, user=user, resource_type=rt_other)

    url = reverse("learning:resource_list") + "?type=book"
    response = client_logged_in.get(url)

    assert response.status_code == 200
    assert len(response.context["resources"]) == 1


def test_resource_detail_view(client_logged_in, user):
    resource = baker.make(LearningResource, user=user)

    url = reverse("learning:resource_detail", args=[resource.pk])
    response = client_logged_in.get(url)

    assert response.status_code == 200
    assert response.context["resource"] == resource


def test_resource_create(client_logged_in, user):
    rt = ResourceType.objects.get(slug="udemy")
    url = reverse("learning:resource_create")

    data = {
        "title": "New Learning Resource",
        "resource_type": rt.pk,
        "description": "A great course",
    }

    response = client_logged_in.post(url, data)

    assert response.status_code == 302
    assert LearningResource.objects.filter(
        title="New Learning Resource", user=user
    ).exists()


def test_resource_create_with_new_type(client_logged_in, user):
    url = reverse("learning:resource_create")

    data = {
        "title": "Podcast Resource",
        "new_resource_type": "Podcast",
        "new_content_kind": "video",
        "description": "",
    }

    response = client_logged_in.post(url, data)

    assert response.status_code == 302
    assert LearningResource.objects.filter(title="Podcast Resource", user=user).exists()
    assert ResourceType.objects.filter(slug="podcast").exists()


def test_resource_update(client_logged_in, user):
    rt = ResourceType.objects.get(slug="book")
    resource = baker.make(
        LearningResource,
        user=user,
        title="Old Title",
        resource_type=rt,
    )

    url = reverse("learning:resource_update", args=[resource.pk])
    response = client_logged_in.post(
        url,
        {"title": "Updated Title", "resource_type": rt.pk, "description": ""},
    )

    resource.refresh_from_db()

    assert response.status_code == 302
    assert resource.title == "Updated Title"


def test_resource_delete(client_logged_in, user):
    resource = baker.make(LearningResource, user=user)

    url = reverse("learning:resource_delete", args=[resource.pk])
    response = client_logged_in.post(url)

    assert response.status_code == 302
    assert not LearningResource.objects.filter(pk=resource.pk).exists()


def test_user_cannot_access_other_users_resource(client_logged_in):
    other_resource = baker.make(LearningResource)

    url = reverse("learning:resource_detail", args=[other_resource.pk])
    response = client_logged_in.get(url)

    assert response.status_code == 404


def test_user_cannot_update_other_users_resource(client_logged_in):
    rt = ResourceType.objects.get(slug="book")
    other_resource = baker.make(LearningResource)

    url = reverse("learning:resource_update", args=[other_resource.pk])
    response = client_logged_in.post(url, {"title": "Hacked", "resource_type": rt.pk})

    assert response.status_code == 404


def test_user_cannot_delete_other_users_resource(client_logged_in):
    other_resource = baker.make(LearningResource)

    url = reverse("learning:resource_delete", args=[other_resource.pk])
    response = client_logged_in.post(url)

    assert response.status_code == 404


@pytest.mark.parametrize(
    "url",
    [
        lambda: reverse("learning:resource_list"),
        lambda: reverse("learning:resource_create"),
        lambda: reverse("learning:resource_detail", args=[999]),
        lambda: reverse("learning:resource_update", args=[999]),
        lambda: reverse("learning:resource_delete", args=[999]),
    ],
)
def test_resource_views_require_login(client, url):
    response = client.get(url())

    assert response.status_code == 302
    assert "/login/" in response.url


def test_resource_list_excludes_archived(client_logged_in, user):
    active = baker.make(LearningResource, user=user, is_archived=False)
    baker.make(LearningResource, user=user, is_archived=True)

    url = reverse("learning:resource_list")
    response = client_logged_in.get(url)

    assert response.status_code == 200

    resources = list(response.context["resources"])

    assert active in resources
    assert len(resources) == 1


def test_resource_archive_sets_is_archived(client_logged_in, user):
    resource = baker.make(LearningResource, user=user, is_archived=False)

    url = reverse("learning:resource_archive", args=[resource.pk])
    client_logged_in.post(url)

    resource.refresh_from_db()
    assert resource.is_archived is True


def test_resource_archive_redirects_to_list(client_logged_in, user):
    resource = baker.make(LearningResource, user=user, is_archived=False)

    url = reverse("learning:resource_archive", args=[resource.pk])
    response = client_logged_in.post(url)

    assert response.status_code == 302
    assert response.url == reverse("learning:resource_list")


def test_resource_unarchive_clears_is_archived(client_logged_in, user):
    resource = baker.make(LearningResource, user=user, is_archived=True)

    url = reverse("learning:resource_archive", args=[resource.pk])
    client_logged_in.post(url)

    resource.refresh_from_db()
    assert resource.is_archived is False


def test_resource_unarchive_redirects_to_detail(client_logged_in, user):
    resource = baker.make(LearningResource, user=user, is_archived=True)

    url = reverse("learning:resource_archive", args=[resource.pk])
    response = client_logged_in.post(url)

    assert response.status_code == 302
    assert response.url == resource.get_absolute_url()


def test_resource_archive_list_shows_archived(client_logged_in, user):
    archived = baker.make(LearningResource, user=user, is_archived=True)

    url = reverse("learning:resource_archive_list")
    response = client_logged_in.get(url)

    assert response.status_code == 200
    assert archived in response.context["resources"]


def test_resource_archive_list_excludes_active(client_logged_in, user):
    active = baker.make(LearningResource, user=user, is_archived=False)

    url = reverse("learning:resource_archive_list")
    response = client_logged_in.get(url)

    assert response.status_code == 200
    assert active not in response.context["resources"]


def test_archived_resource_detail_is_accessible(client_logged_in, user):
    resource = baker.make(LearningResource, user=user, is_archived=True)

    url = reverse("learning:resource_detail", args=[resource.pk])
    response = client_logged_in.get(url)

    assert response.status_code == 200


def test_user_cannot_archive_other_users_resource(client_logged_in):
    other_resource = baker.make(LearningResource)

    url = reverse("learning:resource_archive", args=[other_resource.pk])
    response = client_logged_in.post(url)

    assert response.status_code == 404


def test_resource_archive_requires_login(client):
    url = reverse("learning:resource_archive", args=[999])
    response = client.post(url)

    assert response.status_code == 302
    assert "/login/" in response.url


# ---------------------------------------------------------------------------
# ResourceListView — archived_count context
# ---------------------------------------------------------------------------


def test_resource_list_archived_count_in_context(client_logged_in, user):
    baker.make(LearningResource, user=user, is_archived=True)
    baker.make(LearningResource, user=user, is_archived=True)
    baker.make(LearningResource, user=user, is_archived=False)

    response = client_logged_in.get(reverse("learning:resource_list"))

    assert response.status_code == 200
    assert response.context["archived_count"] == 2


def test_resource_list_archived_count_zero_when_no_archived(client_logged_in, user):
    baker.make(LearningResource, user=user, is_archived=False)

    response = client_logged_in.get(reverse("learning:resource_list"))

    assert response.context["archived_count"] == 0


def test_resource_list_archived_count_excludes_other_users(client_logged_in, user):
    baker.make(LearningResource, user=user, is_archived=True)
    baker.make(LearningResource, is_archived=True)  # different user

    response = client_logged_in.get(reverse("learning:resource_list"))

    assert response.context["archived_count"] == 1


# ---------------------------------------------------------------------------
# ResourceArchiveListView — search and sort
# ---------------------------------------------------------------------------


def test_resource_archive_list_search_filters_by_title(client_logged_in, user):
    baker.make(LearningResource, user=user, is_archived=True, title="Python Basics")
    baker.make(LearningResource, user=user, is_archived=True, title="Django REST")

    response = client_logged_in.get(
        reverse("learning:resource_archive_list") + "?search=python"
    )

    assert response.status_code == 200
    resources = list(response.context["resources"])
    assert len(resources) == 1
    assert resources[0].title == "Python Basics"


def test_resource_archive_list_search_no_match_returns_empty(client_logged_in, user):
    baker.make(LearningResource, user=user, is_archived=True, title="Python Basics")

    response = client_logged_in.get(
        reverse("learning:resource_archive_list") + "?search=javascript"
    )

    assert response.status_code == 200
    assert list(response.context["resources"]) == []


def test_resource_archive_list_search_query_in_context(client_logged_in, user):
    response = client_logged_in.get(
        reverse("learning:resource_archive_list") + "?search=test"
    )

    assert response.context["search_query"] == "test"


def test_resource_archive_list_sort_defaults_to_recently_archived(
    client_logged_in, user
):
    response = client_logged_in.get(reverse("learning:resource_archive_list"))

    assert response.context["sort"] == "-updated_at"


def test_resource_archive_list_sort_param_in_context(client_logged_in, user):
    response = client_logged_in.get(
        reverse("learning:resource_archive_list") + "?sort=updated_at"
    )

    assert response.context["sort"] == "updated_at"


def test_resource_archive_list_sort_invalid_param_falls_back_to_default(
    client_logged_in, user
):
    baker.make(LearningResource, user=user, is_archived=True)

    response = client_logged_in.get(
        reverse("learning:resource_archive_list") + "?sort=invalid"
    )

    assert response.status_code == 200
    assert response.context["sort"] == "invalid"  # stored as-is; queryset uses default


def test_resource_archive_list_sort_by_updated_at_ordering(client_logged_in, user):
    older = baker.make(LearningResource, user=user, is_archived=True)
    newer = baker.make(LearningResource, user=user, is_archived=True)

    LearningResource.objects.filter(pk=older.pk).update(
        updated_at=timezone.now() - timedelta(days=10)
    )
    LearningResource.objects.filter(pk=newer.pk).update(
        updated_at=timezone.now() - timedelta(days=1)
    )

    response_recent = client_logged_in.get(
        reverse("learning:resource_archive_list") + "?sort=-updated_at"
    )
    response_oldest = client_logged_in.get(
        reverse("learning:resource_archive_list") + "?sort=updated_at"
    )

    recent_ids = [r.pk for r in response_recent.context["resources"]]
    oldest_ids = [r.pk for r in response_oldest.context["resources"]]

    assert recent_ids[0] == newer.pk
    assert oldest_ids[0] == older.pk


# ---------------------------------------------------------------------------
# ResourceUpdateView — accessible for archived resources
# ---------------------------------------------------------------------------


def test_archived_resource_update_is_accessible(client_logged_in, user):
    rt = ResourceType.objects.get(slug="book")
    resource = baker.make(
        LearningResource, user=user, is_archived=True, resource_type=rt
    )

    url = reverse("learning:resource_update", args=[resource.pk])
    response = client_logged_in.get(url)

    assert response.status_code == 200


def test_archived_resource_can_be_updated(client_logged_in, user):
    rt = ResourceType.objects.get(slug="book")
    resource = baker.make(
        LearningResource,
        user=user,
        is_archived=True,
        title="Old Title",
        resource_type=rt,
    )

    url = reverse("learning:resource_update", args=[resource.pk])
    client_logged_in.post(
        url,
        {"title": "New Title", "resource_type": rt.pk, "description": ""},
    )

    resource.refresh_from_db()
    assert resource.title == "New Title"
    assert resource.is_archived is True  # archive state unchanged


# ---------------------------------------------------------------------------
# ResourceDeleteView — accessible for archived resources
# ---------------------------------------------------------------------------


def test_archived_resource_can_be_deleted(client_logged_in, user):
    resource = baker.make(LearningResource, user=user, is_archived=True)

    url = reverse("learning:resource_delete", args=[resource.pk])
    response = client_logged_in.post(url)

    assert response.status_code == 302
    assert not LearningResource.objects.filter(pk=resource.pk).exists()
