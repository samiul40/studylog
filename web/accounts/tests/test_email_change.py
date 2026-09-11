from io import StringIO

import pytest
from allauth.account.models import EmailAddress, EmailConfirmationHMAC
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.urls import reverse
from model_bakery import baker

pytestmark = pytest.mark.django_db

User = get_user_model()
SETTINGS_URL = reverse("settings")


@pytest.fixture
def account(user):
    """A consented user whose email is properly registered with allauth."""
    user.email = "old@example.com"
    user.save()
    EmailAddress.objects.create(
        user=user, email="old@example.com", verified=True, primary=True
    )
    return user


def change_email(client, address):
    return client.post(
        SETTINGS_URL, {"form_type": "email", "email": address}, follow=False
    )


def test_the_profile_form_can_no_longer_write_the_email(client_logged_in, account):
    """Saving the name must not touch the address allauth signs people in with."""
    client_logged_in.post(
        SETTINGS_URL,
        {
            "form_type": "profile",
            "first_name": "Sam",
            "last_name": "Amin",
            "email": "sneaky@example.com",
        },
    )

    account.refresh_from_db()
    assert account.email == "old@example.com"
    assert account.first_name == "Sam"


def test_changing_the_email_does_not_take_effect_immediately(
    client_logged_in, account, mailoutbox
):
    change_email(client_logged_in, "new@example.com")

    account.refresh_from_db()
    assert account.email == "old@example.com"


def test_changing_the_email_stores_it_as_pending_and_sends_one_confirmation(
    client_logged_in, account, mailoutbox
):
    change_email(client_logged_in, "new@example.com")

    pending = EmailAddress.objects.get(user=account, email="new@example.com")
    assert pending.verified is False
    assert pending.primary is False

    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["new@example.com"]


def test_confirming_promotes_the_address_and_drops_the_old_one(
    client_logged_in, account, mailoutbox
):
    change_email(client_logged_in, "new@example.com")
    pending = EmailAddress.objects.get(user=account, email="new@example.com")

    key = EmailConfirmationHMAC(pending).key
    client_logged_in.post(reverse("account_confirm_email", args=[key]))

    account.refresh_from_db()
    assert account.email == "new@example.com"

    addresses = EmailAddress.objects.filter(user=account)
    assert [a.email for a in addresses] == ["new@example.com"]
    assert addresses.first().verified is True
    assert addresses.first().primary is True


def test_submitting_the_current_address_changes_nothing(
    client_logged_in, account, mailoutbox
):
    response = change_email(client_logged_in, "old@example.com")

    assert response.status_code == 200
    assert "email" in response.context["email_form"].errors
    assert mailoutbox == []
    assert EmailAddress.objects.filter(user=account).count() == 1


def test_an_address_owned_by_another_account_cannot_be_taken_over(
    client_logged_in, account, mailoutbox
):
    """ACCOUNT_PREVENT_ENUMERATION is on, so allauth deliberately accepts the
    request rather than revealing the address is registered. The real guard is
    at verification: can_set_verified() refuses while another account holds a
    verified copy."""
    other = baker.make(User, email="taken@example.com")
    EmailAddress.objects.create(
        user=other, email="taken@example.com", verified=True, primary=True
    )

    change_email(client_logged_in, "taken@example.com")

    pending = EmailAddress.objects.filter(
        user=account, email="taken@example.com"
    ).first()
    if pending is not None:
        key = EmailConfirmationHMAC(pending).key
        client_logged_in.post(reverse("account_confirm_email", args=[key]))
        pending.refresh_from_db()
        assert pending.verified is False

    account.refresh_from_db()
    assert account.email == "old@example.com"


def test_the_pending_address_is_shown_back_to_the_user(client_logged_in, account):
    change_email(client_logged_in, "new@example.com")

    content = client_logged_in.get(SETTINGS_URL).content.decode()

    assert "new@example.com" in content
    assert "Waiting for confirmation" in content


def test_the_audit_command_reports_a_desynced_account(account):
    # Simulate the old bug: profile address changed, allauth's record left behind.
    User.objects.filter(pk=account.pk).update(email="drifted@example.com")

    out = StringIO()
    call_command("audit_email_sync", stdout=out)
    output = out.getvalue()

    assert "drifted@example.com" in output
    assert "old@example.com" in output


def test_the_audit_command_changes_nothing(account):
    User.objects.filter(pk=account.pk).update(email="drifted@example.com")

    call_command("audit_email_sync", stdout=StringIO())

    account.refresh_from_db()
    assert account.email == "drifted@example.com"
    assert EmailAddress.objects.get(user=account).email == "old@example.com"


def test_the_audit_command_is_quiet_when_everything_matches(account):
    out = StringIO()
    call_command("audit_email_sync", stdout=out)

    assert "in sync" in out.getvalue()


def test_the_allauth_email_page_redirects_to_settings(client_logged_in):
    """Settings does the same job in the app's own design, so there is one
    place to manage email rather than two that can drift."""
    response = client_logged_in.get("/accounts/email/")

    assert response.status_code == 302
    assert response.url == SETTINGS_URL


def test_resending_sends_another_link(client_logged_in, account, mailoutbox):
    change_email(client_logged_in, "new@example.com")
    mailoutbox.clear()
    # allauth throttles verification emails; clear the counter so this tests
    # the resend itself rather than the rate limiter.
    cache.clear()

    client_logged_in.post(SETTINGS_URL, {"form_type": "email_resend"})

    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["new@example.com"]


def test_a_throttled_resend_does_not_claim_it_sent_one(
    client_logged_in, account, mailoutbox
):
    """allauth rate limits verification emails. Saying "we've sent another
    link" when it sent nothing would have people waiting on a mail that is
    never coming."""
    change_email(client_logged_in, "new@example.com")
    mailoutbox.clear()

    response = client_logged_in.post(
        SETTINGS_URL, {"form_type": "email_resend"}, follow=True
    )

    assert mailoutbox == []
    content = response.content.decode()
    assert "sent another link" not in content
    assert "try again shortly" in content


def test_cancelling_drops_the_pending_address(client_logged_in, account):
    change_email(client_logged_in, "new@example.com")

    client_logged_in.post(SETTINGS_URL, {"form_type": "email_cancel"})

    assert not EmailAddress.objects.filter(email="new@example.com").exists()

    account.refresh_from_db()
    assert account.email == "old@example.com"
    assert EmailAddress.objects.get(user=account).email == "old@example.com"


def test_cancelling_never_removes_the_live_address(client_logged_in, account):
    """With nothing pending the action must be a harmless no-op, not a way to
    delete the address you sign in with."""
    client_logged_in.post(SETTINGS_URL, {"form_type": "email_cancel"})

    assert EmailAddress.objects.filter(
        user=account, email="old@example.com", verified=True
    ).exists()
