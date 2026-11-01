"""Results views: Faculty publication (FR-026), the results API (FR-025) and the Student scorecard (FR-027)."""
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from attempts.services import result_visible
from examsetup.views import _faculty_exam_or_403
from identity.access import roles
from repository.models import Attempt, Role

from .services import ResultsNotReady, scorecard, set_results_published


@roles(Role.FACULTY)
@require_POST
def results_publish(request, exam_id):
    """FR-026: the Faculty of the exam's course publishes or unpublishes its results."""
    exam = _faculty_exam_or_403(request, exam_id)
    publish = request.POST.get("publish") == "1"

    try:
        set_results_published(exam, publish)
    except ResultsNotReady as refusal:
        messages.error(request, str(refusal))
    else:
        messages.success(
            request,
            "Results published." if publish else "Results unpublished.",
        )

    return redirect("exam-detail", exam_id=exam.pk)


@roles(Role.STUDENT)
@require_GET
def result_api(request, attempt_id):
    """Return a Student's result only when it belongs to them and is visible."""
    attempt = get_object_or_404(
        Attempt.objects.select_related("exam"),
        pk=attempt_id,
    )

    if attempt.student_id != request.user.pk or not result_visible(attempt):
        raise PermissionDenied

    return JsonResponse(
        {
            "score": str(attempt.score),
            "percentage": str(attempt.percentage),
            "passed": attempt.passed,
        }
    )


@roles(Role.STUDENT)
@require_GET
def scorecard_page(request, attempt_id):
    """FR-027: the Student's own scorecard. 403 for another Student's attempt or an unpublished result (FR-025)."""
    attempt = get_object_or_404(Attempt.objects.select_related("exam"), pk=attempt_id)
    if attempt.student_id != request.user.pk or not result_visible(attempt):
        raise PermissionDenied
    return render(request, "results/scorecard.html", {"attempt": attempt, "card": scorecard(attempt)})
