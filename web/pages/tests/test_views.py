import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

INDEX_URL = reverse("index")


def test_index_redirects_to_dashboard(client):
    response = client.get(INDEX_URL)

    assert response.status_code == 302
    assert response.url == reverse("learning:dashboard")


def test_index_redirects_authenticated_user_to_dashboard(client_logged_in):
    response = client_logged_in.get(INDEX_URL)

    assert response.status_code == 302
    assert response.url == reverse("learning:dashboard")
