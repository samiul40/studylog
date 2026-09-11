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


@pytest.mark.parametrize("name", ["privacy", "terms"])
def test_legal_pages_render_for_anonymous(client, name):
    response = client.get(reverse(name))

    assert response.status_code == 200


@pytest.mark.parametrize("name", ["privacy", "terms"])
def test_legal_pages_are_not_indexed_while_they_are_placeholders(client, name):
    response = client.get(reverse(name))

    assert 'content="noindex"' in response.content.decode()


def test_footer_links_to_the_feature_request_page(client_logged_in):
    response = client_logged_in.get(reverse("learning:dashboard"))

    content = response.content.decode()

    assert "Suggest a feature" in content
    assert reverse("feature_request") in content
