import re

from allauth.account.forms import SignupForm
from allauth.account.utils import filter_users_by_username, user_email, user_field
from allauth.socialaccount.forms import SignupForm as SocialSignupForm
from allauth.utils import generate_unique_username
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
        profile, _ = UserProfile.objects.get_or_create(user=user)

        # Don't overwrite an existing age confirmation — that timestamp should
        # stay at the moment they first confirmed, not the latest re-consent.
        if not profile.age_confirmed:
            profile.age_confirmed = True
            profile.age_confirmed_at = now

        profile.terms_accepted = True
        profile.terms_accepted_at = now
        profile.terms_version = settings.TERMS_VERSION
        profile.privacy_accepted = True
        profile.privacy_accepted_at = now
        profile.privacy_version = settings.PRIVACY_VERSION
        profile.save()


class AcceptTermsForm(TermsAcceptanceMixin, forms.Form):
    """
    Re-consent for an existing account. The age tick is dropped when the user
    has already confirmed it, so a version-only bump doesn't ask again.
    """

    def __init__(self, *args, age_already_confirmed=False, **kwargs):
        super().__init__(*args, **kwargs)
        if age_already_confirmed:
            del self.fields["age_confirmed"]


class StudyLogSignupForm(TermsAcceptanceMixin, SignupForm):
    def save(self, request):
        user = super().save(request)
        self.record_acceptance(user)
        return user


USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")


class StudyLogSocialSignupForm(TermsAcceptanceMixin, SocialSignupForm):
    """
    Google has already told us who the user is, so the only required input is
    consent. The username is optional and prefilled with a suggestion.
    """

    def __init__(self, *args, **kwargs):
        # The kwarg, not fields["username"].required — allauth's clean_username
        # checks this same flag to decide whether a blank value is allowed.
        kwargs.setdefault("username_required", False)
        super().__init__(*args, **kwargs)

        self.suggested_username = self._suggest_username()
        self.fields["username"].label = "Username"
        self.fields["username"].widget.attrs["placeholder"] = self.suggested_username
        if not self.is_bound:
            self.initial["username"] = self.suggested_username

    def _suggest_username(self):
        """Google sends no username, so allauth's initial for it is always
        blank — derive one the same way allauth would at save time."""
        user = self.sociallogin.user
        return generate_unique_username(
            [
                user_field(user, "first_name") or "",
                user_field(user, "last_name") or "",
                user_email(user) or "",
                "user",
            ]
        )

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            # Blank is allowed; allauth generates one during save.
            return ""

        if not USERNAME_RE.match(username):
            raise forms.ValidationError("Use 3–20 letters, numbers or underscores.")

        if filter_users_by_username(username).exists():
            raise forms.ValidationError("That username is already taken.")

        return username

    def save(self, request):
        user = super().save(request)
        self.record_acceptance(user)
        return user
