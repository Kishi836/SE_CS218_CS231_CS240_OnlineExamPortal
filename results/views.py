"""Results views: Faculty publication (FR-026), the results API (FR-025) and the Student scorecard (FR-027)."""
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from attempts.services import result_visible
from identity.access import roles
from repository.models import Attempt, Role

from .services import scorecard


@roles(Role.STUDENT)
@require_GET
def scorecard_page(request, attempt_id):
    """FR-027: the Student's own scorecard. 403 for another Student's attempt or an unpublished result (FR-025)."""
    attempt = get_object_or_404(Attempt.objects.select_related("exam"), pk=attempt_id)
    if attempt.student_id != request.user.pk or not result_visible(attempt):
        raise PermissionDenied
    return render(request, "results/scorecard.html", {"attempt": attempt, "card": scorecard(attempt)})
