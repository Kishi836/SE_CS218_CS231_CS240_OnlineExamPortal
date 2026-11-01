"""NFR-012: lock an account for 15 minutes after 5 failed sign-ins within 15 minutes.

Failures are counted per email typed -- also for emails with no account, so the lockout message
doesn't reveal which emails exist. The values live in settings, not in this code.
"""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from repository.models import SignInFailure


def _window():
    return timedelta(minutes=settings.SIGNIN_LOCK_MINUTES)


def is_locked(email, now=None):
    """True while `email` has SIGNIN_LOCK_THRESHOLD or more failures in the last SIGNIN_LOCK_MINUTES.

    The window slides, so the lock lifts by itself 15 minutes after the 5th failure.
    """
    now = now or timezone.now()
    recent = SignInFailure.objects.filter(email=email.lower(), at__gt=now - _window()).count()
    return recent >= settings.SIGNIN_LOCK_THRESHOLD


def record_failure(email):
    """One failed sign-in for `email` (stored lower-cased)."""
    SignInFailure.objects.create(email=email.lower())


def clear(email):
    """A successful sign-in wipes the count, so old failures can't add up with new ones."""
    SignInFailure.objects.filter(email=email.lower()).delete()
