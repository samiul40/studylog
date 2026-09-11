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


def test_privacy_is_not_indexed_while_it_is_a_placeholder(client):
    response = client.get(reverse("privacy"))

    assert 'content="noindex"' in response.content.decode()


def test_terms_serves_the_real_document(client):
    response = client.get(reverse("terms"))

    content = response.content.decode()

    assert "Last Updated" in content
    assert "Governing Law" in content
    assert "studyloguk@gmail.com" in content
    assert 'content="noindex"' not in content


@pytest.mark.parametrize("name", ["privacy", "terms"])
def test_legal_pages_give_signed_out_visitors_a_way_back(client, name):
    """Signed out there is no appbar or footer, so the page needs its own link."""
    response = client.get(reverse(name))

    assert "Back to home" in response.content.decode()


@pytest.mark.parametrize("name", ["privacy", "terms"])
def test_legal_pages_omit_the_back_link_when_signed_in(client_logged_in, name):
    response = client_logged_in.get(reverse(name))

    assert "Back to home" not in response.content.decode()


def test_landing_page_links_to_the_legal_pages(client):
    response = client.get(INDEX_URL)

    content = response.content.decode()

    assert reverse("terms") in content
    assert reverse("privacy") in content


def test_footer_links_to_the_feature_request_page(client_logged_in):
    response = client_logged_in.get(reverse("learning:dashboard"))

    content = response.content.decode()

    assert "Suggest a feature" in content
    assert reverse("feature_request") in content
