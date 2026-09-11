import pytest
from django.conf import settings as django_settings
from django.core.cache import cache
from model_bakery import baker


@pytest.fixture(autouse=True)
def clear_cache():
    """Rate limiters (django_ratelimit, and allauth's verification-email
    limiter) count in the process-wide cache, which outlives the per-test
    database rollback. Without this one test silently eats another's
    allowance and the second sends no mail."""
    cache.clear()


@pytest.fixture(autouse=True)
def fast_password_hashing(settings):
    """Django's default PBKDF2 hasher costs ~0.6s per test, and almost every
    test builds a user, so it dominates the suite. MD5 is a real hasher, so
    login and password-change tests still exercise the same code paths.

    This belongs in conftest only. In settings.py it would hash live users'
    passwords with MD5."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def record_consent(user):
    """Mark a user as having accepted the current policies.

    TermsAcceptanceMiddleware redirects anyone whose recorded version doesn't
    match, so without this every authenticated test bounces to the consent
    page. Tests covering the gate itself deliberately skip this."""
    profile = user.profile
    profile.age_confirmed = True
    profile.terms_accepted = True
    profile.terms_version = django_settings.TERMS_VERSION
    profile.privacy_accepted = True
    profile.privacy_version = django_settings.PRIVACY_VERSION
    profile.save()
    return user


@pytest.fixture
def user(db):
    user = baker.make(
        "auth.User", username="testuser", is_superuser=True, is_staff=True
    )
    user.set_password("12345")
    user.save()
    return record_consent(user)


@pytest.fixture
def client_logged_in(client, user):
    client.force_login(user)
    return client
