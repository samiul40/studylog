from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Report accounts where User.email disagrees with allauth's verified "
        "primary EmailAddress. Reads only — it never changes data, because "
        "guessing which address the user intended could strand their account "
        "recovery on one they no longer control."
    )

    def handle(self, *args, **options):
        mismatched = []
        missing = []

        for user in User.objects.all().order_by("pk"):
            primary = EmailAddress.objects.filter(
                user=user, primary=True, verified=True
            ).first()

            if primary is None:
                missing.append(user)
            elif (primary.email or "").lower() != (user.email or "").lower():
                mismatched.append((user, primary.email))

        if mismatched:
            self.stdout.write(
                self.style.WARNING(
                    f"{len(mismatched)} account(s) where the sign-in address "
                    f"differs from the profile address:"
                )
            )
            for user, primary_email in mismatched:
                self.stdout.write(
                    f"  {user.pk} {user.username}: "
                    f"profile={user.email or '(none)'} signs-in-with={primary_email}"
                )

        if missing:
            self.stdout.write(
                self.style.WARNING(
                    f"\n{len(missing)} account(s) with no verified primary "
                    f"address (they cannot reset their password):"
                )
            )
            for user in missing:
                self.stdout.write(
                    f"  {user.pk} {user.username}: {user.email or '(none)'}"
                )

        if not mismatched and not missing:
            self.stdout.write(self.style.SUCCESS("All accounts are in sync."))
