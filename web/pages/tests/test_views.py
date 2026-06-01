import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

INDEX_URL = reverse("index")


def test_index_renders_landing_page_for_anonymous(client):
    response = client.get(INDEX_URL)

    assert response.status_code == 200
    assert b"StudyLog" in response.content


def test_index_redirects_authenticated_user_to_dashboard(client_logged_in):
    response = client_logged_in.get(INDEX_URL)

    assert response.status_code == 302
    assert response.url == reverse("learning:dashboard")
