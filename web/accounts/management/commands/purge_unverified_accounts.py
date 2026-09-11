from datetime import timedelta

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

User = get_user_model()

UNVERIFIED_RETENTION_DAYS = 30


class Command(BaseCommand):
    help = (
        f"Permanently delete accounts that never confirmed their email and "
        f"signed up more than {UNVERIFIED_RETENTION_DAYS} days ago. They "
        f"cannot sign in, and they hold their email address against a fresh "
        f"signup. Reports only unless --delete is given."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Actually delete. Without this, only reports.",
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=UNVERIFIED_RETENTION_DAYS)

        expired = []
        for user in User.objects.filter(date_joined__lt=cutoff).order_by("pk"):
            # Never sweep away an admin account that happens to be stuck.
            if user.is_superuser or user.is_staff:
                continue

            # purge_deleted_accounts owns anything already asked to be removed.
            profile = getattr(user, "profile", None)
            if profile is not None and profile.deletion_requested_at is not None:
                continue

            if EmailAddress.objects.filter(user=user, verified=True).exists():
                continue

            expired.append(user)

        if not expired:
            self.stdout.write("No unverified accounts to purge.")
            return

        if not options["delete"]:
            self.stdout.write(
                f"Would permanently delete {len(expired)} unverified account(s):"
            )
            for user in expired:
                self.stdout.write(
                    f"  {user.pk} {user.username}: {user.email or '(none)'} "
                    f"(joined {user.date_joined:%Y-%m-%d})"
                )
            self.stdout.write("\nRe-run with --delete to actually remove them.")
            return

        deleted = 0
        for user in expired:
            label = f"{user.username} <{user.email or 'no email'}>"
            user.delete()  # cascades to profile, email addresses, learning data
            deleted += 1
            self.stdout.write(f"Deleted account: {label}")

        self.stdout.write(
            self.style.SUCCESS(f"Purged {deleted} unverified account(s).")
        )
