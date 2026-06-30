from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import UserProfile
from accounts.views import ACCOUNT_RETENTION_DAYS

User = get_user_model()


class Command(BaseCommand):
    help = (
        f"Permanently delete accounts that have been soft-deleted for more "
        f"than {ACCOUNT_RETENTION_DAYS} days."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without deleting anything.",
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=ACCOUNT_RETENTION_DAYS)
        expired = UserProfile.objects.filter(
            deletion_requested_at__lte=cutoff
        ).select_related("user")

        count = expired.count()
        if count == 0:
            self.stdout.write("No accounts to purge.")
            return

        if options["dry_run"]:
            self.stdout.write(f"Would permanently delete {count} account(s):")
            for profile in expired:
                self.stdout.write(
                    f"  - {profile.user.email} "
                    f"(requested {profile.deletion_requested_at})"
                )
            return

        deleted = 0
        for profile in expired:
            email = profile.user.email
            profile.user.delete()  # cascades to profile + all learning data
            deleted += 1
            self.stdout.write(f"Deleted account: {email}")

        self.stdout.write(
            self.style.SUCCESS(f"Purged {deleted} account(s) successfully.")
        )
