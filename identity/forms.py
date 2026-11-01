from django import forms
from django.conf import settings
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.utils import timezone

from repository.models import Role, User


class RegistrationForm(forms.ModelForm):
    """Public Student registration form for FR-001."""

    password1 = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput,
        error_messages={"required": "Password is required"},
    )
    password2 = forms.CharField(
        label="Confirm password",
        strip=False,
        widget=forms.PasswordInput,
        error_messages={"required": "Please confirm your password"},
    )
    roll_number = forms.CharField(
        label="Roll number",
        required=True,
        error_messages={"required": "Roll number is required"},
    )
    consent = forms.BooleanField(
        label="I consent to my name, email and roll number being used only to run my examinations.",
        required=True,
        error_messages={"required": "You must consent to register"},
    )

    class Meta:
        model = User
        fields = ("full_name", "email", "roll_number")
        labels = {
            "full_name": "Full name",
            "email": "Institutional email address",
            "roll_number": "Roll number",
        }

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        domain = settings.STUDENT_EMAIL_DOMAIN.lower()
        if not email.endswith(f"@{domain}"):
            raise ValidationError("Please register with your institutional email address")
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists")
        return email

    def clean_roll_number(self):
        roll_number = self.cleaned_data["roll_number"]
        if User.objects.filter(roll_number=roll_number).exists():
            raise ValidationError("This roll number is already registered")
        return roll_number

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Passwords do not match")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = Role.STUDENT
        user.set_password(self.cleaned_data["password1"])
        user.consent_given_at = timezone.now()
        if commit:
            user.save()
        return user


class EmailLoginForm(forms.Form):
    """AuthenticationForm-compatible form that exposes email as the credential."""

    email = forms.EmailField(label="Email address")
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput,
        error_messages={"required": "Password is required"},
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        password = cleaned_data.get("password")
        if email and password:
            self.user_cache = authenticate(self.request, username=email, password=password)
            if self.user_cache is None:
                raise ValidationError("Invalid email or password")
            if not self.user_cache.is_active:
                raise ValidationError("Invalid email or password")
        return cleaned_data

    def get_user(self):
        return self.user_cache
