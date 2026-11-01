"""Integrity (SAD 3.1): focus-loss events during an attempt (FR-028)."""
from attempts.services import AttemptClosed, close_if_expired
from repository.models import FocusEvent  # noqa: F401


def record_focus_loss(attempt):
    """FR-028: one FocusEvent for one loss of focus, stamped by the server (FocusEvent.occurred_at is auto_now_add).

    Nothing from the browser goes into the row -- not even a time (UT_067). A submitted or expired attempt
    is no longer "active", so it refuses with AttemptClosed, like save_answer does.
    """
    attempt = close_if_expired(attempt)
    if attempt.submitted_at:
        raise AttemptClosed("This attempt has already been submitted")
    return FocusEvent.objects.create(attempt=attempt)


def events_by_attempt(exam):
    """FR-028: for the Faculty integrity page -- [(attempt, [events...]), ...] for every attempt on `exam`."""
    attempts = exam.attempts.select_related("student").prefetch_related("focus_events").order_by("student__full_name")
    return [(attempt, list(attempt.focus_events.all())) for attempt in attempts]
