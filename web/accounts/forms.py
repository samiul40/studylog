from allauth.account.forms import SignupForm
from allauth.socialaccount.forms import SignupForm as SocialSignupForm
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    PasswordChangeForm as DjangoPasswordChangeForm,
)
from django.utils import timezone

from .models import UserProfile

User = get_user_model()

_FC = {"class": "form-control"}

# Curated grouped choices: (group label, [(iana_key, display_label), ...])
# Django renders nested tuples as <optgroup> elements.
_TIMEZONE_CHOICES = [
    (
        "Europe",
        [
            ("Europe/London", "London / Dublin (GMT/BST)"),
            ("Europe/Lisbon", "Lisbon (WET/WEST)"),
            ("Europe/Paris", "Paris / Berlin / Rome / Madrid (CET/CEST)"),
            ("Europe/Helsinki", "Helsinki / Athens / Kyiv (EET/EEST)"),
            ("Europe/Moscow", "Moscow / Istanbul (MSK)"),
        ],
    ),
    (
        "Americas",
        [
            ("America/New_York", "New York / Toronto (ET)"),
            ("America/Chicago", "Chicago / Mexico City (CT)"),
            ("America/Denver", "Denver / Salt Lake City (MT)"),
            ("America/Phoenix", "Phoenix (MST, no DST)"),
            ("America/Los_Angeles", "Los Angeles / Vancouver (PT)"),
            ("America/Anchorage", "Anchorage (AKT)"),
            ("Pacific/Honolulu", "Honolulu / Hawaii (HST)"),
            ("America/Halifax", "Halifax / Atlantic Canada (AT)"),
            ("America/Sao_Paulo", "São Paulo / Brasília (BRT)"),
            ("America/Argentina/Buenos_Aires", "Buenos Aires (ART)"),
            ("America/Bogota", "Bogotá / Lima / Quito (COT)"),
        ],
    ),
    (
        "Africa & Middle East",
        [
            ("Africa/Lagos", "Lagos (WAT)"),
            ("Africa/Nairobi", "Nairobi / Addis Ababa (EAT)"),
            ("Africa/Cairo", "Cairo (EET)"),
            ("Africa/Johannesburg", "Johannesburg / Harare (SAST)"),
            ("Asia/Dubai", "Dubai / Abu Dhabi (GST)"),
            ("Asia/Riyadh", "Riyadh / Baghdad (AST)"),
            ("Asia/Tehran", "Tehran (IRST)"),
        ],
    ),
    (
        "Asia & South Asia",
        [
            ("Asia/Karachi", "Karachi / Islamabad (PKT)"),
            ("Asia/Kolkata", "India (IST)"),
            ("Asia/Dhaka", "Dhaka / Bangladesh (BST)"),
            ("Asia/Kathmandu", "Kathmandu (NPT)"),
            ("Asia/Colombo", "Colombo / Sri Lanka (SLST)"),
            ("Asia/Yangon", "Yangon / Myanmar (MMT)"),
            ("Asia/Bangkok", "Bangkok / Jakarta (ICT/WIB)"),
            ("Asia/Singapore", "Singapore / Hong Kong / KL (SGT)"),
            ("Asia/Shanghai", "China / Beijing (CST)"),
            ("Asia/Tokyo", "Tokyo / Seoul (JST/KST)"),
        ],
    ),
    (
        "Pacific",
        [
            ("Australia/Perth", "Perth (AWST)"),
            ("Australia/Adelaide", "Adelaide (ACST/ACDT)"),
            ("Australia/Sydney", "Sydney / Melbourne (AEST/AEDT)"),
            ("Pacific/Auckland", "Auckland / Wellington (NZST/NZDT)"),
            ("Pacific/Fiji", "Fiji (FJT)"),
        ],
    ),
    (
        "UTC",
        [
            ("UTC", "UTC (Coordinated Universal Time)"),
        ],
    ),
]


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        widgets = {
            "first_name": forms.TextInput(attrs=_FC),
            "last_name": forms.TextInput(attrs=_FC),
            "email": forms.EmailInput(attrs=_FC),
        }
        labels = {
            "first_name": "First Name",
            "last_name": "Last Name",
            "email": "Email Address",
        }

    def clean_email(self):
        email = self.cleaned_data["email"]
        qs = User.objects.filter(email=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("This email is already in use.")
        return email


class TimezoneForm(forms.ModelForm):
    timezone = forms.ChoiceField(
        choices=_TIMEZONE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Timezone",
    )

    class Meta:
        model = UserProfile
        fields = ["timezone"]


class ChangePasswordForm(DjangoPasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update(_FC)


class TermsAcceptanceMixin(forms.Form):
    """
    Shared by the email and Google signup forms so the two paths can't drift.
    """

    age_confirmed = forms.BooleanField(
        required=True,
        label="I confirm that I am at least 13 years old.",
        error_messages={
            "required": "Please confirm that you are at least 13 years old."
        },
    )
    accept_terms = forms.BooleanField(
        required=True,
        label="I have read and agree to the Terms & Conditions and Privacy Policy.",
        error_messages={
            "required": "Please accept the Terms & Conditions and Privacy Policy."
        },
    )

    def record_acceptance(self, user):
        now = timezone.now()
        profile = user.profile
        profile.age_confirmed = True
        profile.age_confirmed_at = now
        profile.terms_accepted = True
        profile.terms_accepted_at = now
        profile.terms_version = settings.TERMS_VERSION
        profile.privacy_accepted = True
        profile.privacy_accepted_at = now
        profile.privacy_version = settings.PRIVACY_VERSION
        profile.save()


class StudyLogSignupForm(TermsAcceptanceMixin, SignupForm):
    def save(self, request):
        user = super().save(request)
        self.record_acceptance(user)
        return user


class StudyLogSocialSignupForm(TermsAcceptanceMixin, SocialSignupForm):
    def save(self, request):
        user = super().save(request)
        self.record_acceptance(user)
        return user
