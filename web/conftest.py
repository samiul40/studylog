import pytest
from model_bakery import baker


@pytest.fixture(autouse=True)
def fast_password_hashing(settings):
    """Django's default PBKDF2 hasher costs ~0.6s per test, and almost every
    test builds a user, so it dominates the suite. MD5 is a real hasher, so
    login and password-change tests still exercise the same code paths.

    This belongs in conftest only. In settings.py it would hash live users'
    passwords with MD5."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def user(db):
    user = baker.make(
        "auth.User", username="testuser", is_superuser=True, is_staff=True
    )
    user.set_password("12345")
    user.save()
    return user


@pytest.fixture
def client_logged_in(client, user):
    client.force_login(user)
    return client
