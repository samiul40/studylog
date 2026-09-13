import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from faker import Faker

from learning.management.commands._seed import refuse_in_production, seeded_users
from learning.models import Category, LearningResource, LearningUnit, ResourceType


class Command(BaseCommand):
    help = (
        "Seed learning resources and units with fake data. Fills out the first "
        "account by default, or every seeded account with --seeded-users, which "
        "is the second step of the seed_retention pipeline."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--seeded-users",
            action="store_true",
            help=(
                "Give every account from seed_users a resource to study, "
                "instead of loading up the first user in the database."
            ),
        )
        parser.add_argument("--force", action="store_true", help="Run with DEBUG off.")

    def handle(self, *args, **kwargs):
        # Guards the whole command, not just --seeded-users: loading eight fake
        # resources onto whichever account happens to be first in a production
        # table is no better than inventing the accounts outright.
        if refuse_in_production(self, kwargs["force"]):
            return

        fake = Faker()

        User = get_user_model()
        if kwargs["seeded_users"]:
            users = list(seeded_users())
            # One resource each: the point is somewhere to hang sessions, and
            # eight apiece across a few hundred accounts is a lot of rows for
            # a page nobody is going to read.
            per_user = 1
        else:
            users = list(User.objects.all()[:1])
            per_user = 8

        if not users:
            self.stdout.write(self.style.ERROR("No users found. Create a user first."))
            return

        resource_types = list(ResourceType.objects.all())

        if not resource_types:
            self.stdout.write(
                self.style.ERROR("No resource types found. Run migrations first.")
            )
            return

        self.stdout.write(self.style.SUCCESS("Creating learning resources..."))

        resources = []
        for user in users:
            # None included so some resources land in the "Other" bucket on the
            # list page.
            categories = list(Category.objects.for_user(user)) + [None]
            for _ in range(per_user):
                resources.append(
                    LearningResource.objects.create(
                        user=user,
                        title=fake.sentence(nb_words=4),
                        resource_type=random.choice(resource_types),
                        category=random.choice(categories),
                        description=fake.text(max_nb_chars=120),
                    )
                )

        self.stdout.write(self.style.SUCCESS("Creating learning units..."))

        for resource in resources:
            unit_count = random.randint(5, 20)
            is_reading = resource.resource_type.content_kind == "reading"
            unit_label = resource.resource_type.unit_label  # property

            for i in range(1, unit_count + 1):
                status = random.choice(LearningUnit.StatusChoices.values)

                duration = None
                progress = None

                if not is_reading:
                    duration = random.randint(5, 25)
                    if status == LearningUnit.StatusChoices.IN_PROGRESS:
                        progress = random.randint(1, duration)
                    elif status == LearningUnit.StatusChoices.COMPLETED:
                        progress = duration

                LearningUnit.objects.create(
                    resource=resource,
                    title=f"{unit_label} {i}: {fake.sentence(nb_words=3)}",
                    order=i,
                    duration_minutes=duration,
                    status=status,
                    video_progress_minutes=progress,
                    notes=(fake.text(max_nb_chars=80) if random.random() < 0.3 else ""),
                )

        self.stdout.write(self.style.SUCCESS("Learning data successfully seeded!"))
