"""Shared bits of the seed_* commands.

Named with a leading underscore so Django's command discovery skips it.
"""

from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()

# Every account the seeders invent is named with this. It is what --clear
# finds, and what keeps a seeder from touching a real account.
SEED_PREFIX = "seed_cohort_"


def seeded_users():
    return User.objects.filter(username__startswith=SEED_PREFIX)


def refuse_in_production(command, force):
    """True when the command should stop rather than invent data.

    Seeded accounts are counted by rollup_usage_stats and the cohort rollup
    alike, and those tables are deliberately never rewritten — fake signups
    let into a real database can't be taken back out of the history.
    """
    if settings.DEBUG or force:
        return False

    command.stderr.write(
        command.style.ERROR(
            "Refusing to seed fake data with DEBUG off. Pass --force if this "
            "really is a throwaway database."
        )
    )
    return True
