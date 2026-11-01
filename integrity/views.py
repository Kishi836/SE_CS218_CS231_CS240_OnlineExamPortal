"""Integrity views: focus-loss capture and the Faculty integrity page (FR-028), the Admin audit viewer (FR-030)."""

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from attempts.services import AttemptClosed
from examsetup.views import _faculty_exam_or_403
from identity.access import roles
from repository.models import Attempt, AuditEntry, Role

from . import services


@roles(Role.ADMIN)
@require_GET
def audit_log(request):
    """FR-030: Read-only audit log, newest first, with optional entity filters."""
    entries = AuditEntry.objects.select_related("actor")

    entity = request.GET.get("entity", "").strip()
    entity_id = request.GET.get("entity_id", "").strip()

    if entity:
        entries = entries.filter(entity=entity)

    if entity_id.isdigit():
        entries = entries.filter(entity_id=int(entity_id))

    entries = entries[:500]

    return render(
        request,
        "integrity/audit_log.html",
        {"entries": entries},
    )


@roles(Role.STUDENT)
@require_POST
def focus_lost(request, pk):
    """FR-028: Record focus loss during an attempt. Return 204 on success."""
    attempt = get_object_or_404(Attempt, pk=pk, student=request.user)

    try:
        services.record_focus_loss(attempt)
    except AttemptClosed as error:
        return JsonResponse({"detail": str(error)}, status=409)

    return HttpResponse(status=204)


@roles(Role.FACULTY)
@require_GET
def exam_integrity(request, exam_id):
    """FR-028: Display focus-loss counts and event timestamps for a faculty exam."""
    exam = _faculty_exam_or_403(request, exam_id)

    return render(
        request,
        "integrity/exam_integrity.html",
        {
            "exam": exam,
            "attempt_events": services.events_by_attempt(exam),
        },
    )
