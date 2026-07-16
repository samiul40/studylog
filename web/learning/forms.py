from django import forms
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from .models.activity import Activity
from .models.learning_resource import LearningResource
from .models.learning_unit import LearningUnit
from .models.resource_type import ResourceType
from .models.study_session import StudySession


class LearningResourceForm(forms.ModelForm):
    resource_type = forms.ModelChoiceField(
        queryset=ResourceType.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Resource Type",
        empty_label="-- Select a type --",
    )
    new_resource_type = forms.CharField(
        required=False,
        max_length=100,
        label="Or add a new type",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "e.g. Podcast, Blog, Conference Talk",
            }
        ),
    )
    new_content_kind = forms.ChoiceField(
        required=False,
        choices=[("", "-- Content kind --")] + ResourceType.ContentKind.choices,
        label="Content kind",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    unit_count = forms.IntegerField(
        required=False,
        min_value=1,
        label="Number of units",
        widget=forms.NumberInput(
            attrs={"class": "form-control", "placeholder": "e.g. 10"}
        ),
    )
    youtube_units = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user is not None:
            self.fields["resource_type"].queryset = ResourceType.objects.filter(
                Q(is_system=True) | Q(user=user)
            )

    class Meta:
        model = LearningResource
        fields = ["title", "resource_type", "description", "url"]

        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. Django Course",
                }
            ),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "url": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://example.com",
                }
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        resource_type = cleaned_data.get("resource_type")
        new_name = cleaned_data.get("new_resource_type", "").strip()

        if not new_name and not resource_type:
            raise forms.ValidationError(
                "Please select an existing type or add a new one."
            )

        return cleaned_data

    def save(self, commit=True):
        new_name = self.cleaned_data.get("new_resource_type", "").strip()
        if new_name:
            new_kind = self.cleaned_data.get("new_content_kind", "").strip()
            slug = slugify(new_name)
            rt, _ = ResourceType.objects.get_or_create(
                slug=slug,
                user=self.user,
                defaults={
                    "name": new_name,
                    "content_kind": (new_kind or ResourceType.ContentKind.VIDEO),
                },
            )
            self.instance.resource_type = rt
        return super().save(commit=commit)


class StudySessionForm(forms.ModelForm):
    # Accepts a new custom activity name; find-or-create handled in the view.
    new_activity_name = forms.CharField(
        required=False,
        max_length=32,
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._user = user
        if not self.instance.pk:
            self.fields["date"].initial = timezone.localdate()
        # activity can be empty when the user is creating a new custom one
        self.fields["activity"].required = False
        if user is not None:
            self.fields["resource"].queryset = (
                LearningResource.objects.for_user(user).active().order_by("title")
            )
            self.fields["unit"].queryset = LearningUnit.objects.filter(
                resource__user=user
            ).order_by("resource_id", "order")
            self.fields["activity"].queryset = Activity.objects.for_user(user).order_by(
                "-is_system", "name"
            )
        else:
            self.fields["resource"].queryset = LearningResource.objects.none()
            self.fields["unit"].queryset = LearningUnit.objects.none()
            self.fields["activity"].queryset = Activity.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        unit = cleaned_data.get("unit")
        resource = cleaned_data.get("resource")
        if unit and resource and unit.resource != resource:
            self.add_error(
                "unit", "This unit does not belong to the selected resource."
            )
        activity = cleaned_data.get("activity")
        new_name = cleaned_data.get("new_activity_name", "").strip()
        if not activity and not new_name:
            raise forms.ValidationError("Please select an activity or type a new one.")
        return cleaned_data

    class Meta:
        model = StudySession
        fields = [
            "status",
            "activity",
            "resource",
            "unit",
            "date",
            "duration_minutes",
            "title",
            "topic",
            "notes",
        ]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "activity": forms.HiddenInput(),
            "resource": forms.Select(attrs={"class": "form-select"}),
            "unit": forms.HiddenInput(),
            "duration_minutes": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "e.g. 30"}
            ),
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. June 2019 Chem Paper 2",
                }
            ),
            "topic": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. Glycolysis",
                }
            ),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def clean_duration_minutes(self):
        duration = self.cleaned_data.get("duration_minutes")
        if duration is not None and duration < 1:
            raise forms.ValidationError("Duration must be at least 1 minute.")
        return duration

    def clean_date(self):
        date = self.cleaned_data.get("date")
        status = self.cleaned_data.get("status")
        if (
            date
            and date > timezone.localdate()
            and status != StudySession.Status.PLANNED
        ):
            raise forms.ValidationError(
                "Future dates are only allowed when planning a session."
            )
        return date


class LearningUnitForm(forms.ModelForm):
    def clean(self):
        cleaned_data = super().clean()

        duration = cleaned_data.get("duration_minutes")
        progress = cleaned_data.get("video_progress_minutes")

        if duration and progress and progress > duration:
            self.add_error(
                "video_progress_minutes",
                "Progress cannot exceed total duration.",
            )

        return cleaned_data

    class Meta:
        model = LearningUnit
        fields = [
            "title",
            "duration_minutes",
            "notes",
            "video_progress_minutes",
        ]

        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "duration_minutes": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "e.g. 15"}
            ),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "video_progress_minutes": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "e.g. 10"}
            ),
        }
