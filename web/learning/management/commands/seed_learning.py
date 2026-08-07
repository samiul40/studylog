import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from faker import Faker

from learning.models import Category, LearningResource, LearningUnit, ResourceType


class Command(BaseCommand):
    help = "Seed learning resources and units with fake data"

    def handle(self, *args, **kwargs):
        fake = Faker()

        User = get_user_model()
        user = User.objects.first()

        if not user:
            self.stdout.write(self.style.ERROR("No users found. Create a user first."))
            return

        resource_types = list(ResourceType.objects.all())

        if not resource_types:
            self.stdout.write(
                self.style.ERROR("No resource types found. Run migrations first.")
            )
            return

        self.stdout.write(self.style.SUCCESS("Creating learning resources..."))

        # None included so some resources land in the "Other" bucket on the list page.
        categories = list(Category.objects.for_user(user)) + [None]

        resources = []
        for _ in range(8):
            resource = LearningResource.objects.create(
                user=user,
                title=fake.sentence(nb_words=4),
                resource_type=random.choice(resource_types),
                category=random.choice(categories),
                description=fake.text(max_nb_chars=120),
            )
            resources.append(resource)

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
