import pytest
from conftest import record_consent
from django.contrib.auth.models import Permission
from django.urls import reverse
from model_bakery import baker

pytestmark = pytest.mark.django_db


def test_authenticated_user_without_permission_redirects_to_index(client):
    """Authenticated user lacking the required permission gets redirected to
    index, not a 403."""
    user = record_consent(baker.make("auth.User", is_superuser=False, is_staff=False))
    user.set_password("pass")
    user.save()
    client.force_login(user)

    # ResourceListView requires learning.view_learningresource
    url = reverse("learning:resource_list")
    response = client.get(url)

    assert response.status_code == 302
    assert response.url == reverse("index")


def test_authenticated_user_with_permission_is_not_redirected(client):
    """Authenticated user who has the required permission reaches the view."""
    user = record_consent(baker.make("auth.User", is_superuser=False, is_staff=False))
    user.set_password("pass")
    user.save()
    perm = Permission.objects.get(codename="view_learningresource")
    user.user_permissions.add(perm)
    client.force_login(user)

    url = reverse("learning:resource_list")
    response = client.get(url)

    assert response.status_code == 200


def test_unauthenticated_user_redirects_to_login(client):
    """Unauthenticated user is sent to the login page, not index."""
    url = reverse("learning:resource_list")
    response = client.get(url)

    assert response.status_code == 302
    assert "/login/" in response.url
