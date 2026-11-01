
"""Student exam visibility and attempt session management."""

import math

from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from identity.access import roles
from repository.models import Attempt, Exam, Option, Question, Role

from . import services
from .services import AttemptClosed, close_if_expired, expires_at, remaining_seconds


class NotEligible(Exception):
    """A start refused for a reason the Student is told (FR-015)."""


def start(exam, student):
    """Refuse ineligible students; otherwise return their server-created attempt."""
    if (
        exam.status != Exam.Status.PUBLISHED
        or not exam.course.students.filter(pk=student.pk).exists()
    ):
        raise PermissionDenied

    # FR-021: the window gates only a new attempt. One already started resumes until its own expiry,
    # even if the window has closed since.
    if not Attempt.objects.filter(exam=exam, student=student).exists():
        now = timezone.now()

        if exam.window_start is None or exam.window_end is None or now < exam.window_start:
            raise NotEligible("This examination has not opened yet")

        if now >= exam.window_end:
            raise NotEligible("This examination has closed")

    attempt, _ = Attempt.objects.get_or_create(exam=exam, student=student)

    if close_if_expired(attempt).submitted_at:
        raise NotEligible("You have already submitted this examination")

    return attempt


def paper(attempt):
    """Return exam questions and option text without exposing correct answers."""
    questions = attempt.exam.questions.order_by("examquestion__order")
    return [
        {
            "id": question.id,
            "stem": question.stem,
            "options": list(question.options.values("id", "text")),
        }
        for question in questions
    ]


@roles(Role.STUDENT)
@require_GET
def student_exam_list(request):
    """Show published exams belonging to courses the student is enrolled in."""
    exams = services.visible_exams(request.user).order_by("title")

    return render(
        request,
        "attempts/student_exam_list.html",
        {"exams": exams},
    )


@roles(Role.STUDENT)
@require_GET
def student_exam_detail(request, exam_id):
    """Show an exam to enrolled students; forbid access by other students."""
    exam = get_object_or_404(
        Exam.objects.select_related("course").filter(
            status=Exam.Status.PUBLISHED,
        ),
        pk=exam_id,
    )

    if not exam.course.students.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    return render(
        request,
        "attempts/student_exam_detail.html",
        {"exam": exam},
    )


@roles(Role.STUDENT)
@require_POST
def start_attempt(request):
    exam_id = request.POST.get("exam", "")

    if not exam_id.isdigit():
        raise Http404

    try:
        attempt = start(get_object_or_404(Exam, pk=exam_id), request.user)
    except NotEligible as refusal:
        return render(
            request,
            "attempts/refused.html",
            {"message": str(refusal)},
            status=403,
        )

    return redirect("attempt-paper", attempt.pk)


@roles(Role.STUDENT)
def attempt_paper(request, pk):
    """Deliver the student's attempt paper, or show its submitted state."""
    attempt = close_if_expired(
        get_object_or_404(Attempt, pk=pk, student=request.user)
    )

    if attempt.submitted_at:
        timed_out = attempt.submitted_at == expires_at(attempt)
        return render(
            request,
            "attempts/submitted.html",
            {"attempt": attempt, "timed_out": timed_out},
        )

    return redirect("attempt-question", attempt.pk, 1)


@roles(Role.STUDENT)
@require_GET
def attempt_question(request, pk, n):
    """FR-018: question `n` (1-based) of the Student's attempt, with the palette for the whole paper."""
    attempt = close_if_expired(get_object_or_404(Attempt, pk=pk, student=request.user))
    if attempt.submitted_at:
        return redirect("attempt-paper", attempt.pk)  # shows the submitted page

    questions = paper(attempt)
    if not 1 <= n <= len(questions):
        raise Http404
    question = questions[n - 1]

    services.visit(attempt, question["id"])
    states = services.palette(attempt, [q["id"] for q in questions])
    saved = attempt.answers.get(question_id=question["id"])
    expires_in = math.ceil((expires_at(attempt) - timezone.now()).total_seconds())
    return render(request, "attempts/question.html", {
        "attempt": attempt, "question": question, "n": n, "total": len(questions),
        "cells": list(enumerate(states, start=1)), "saved": saved.option_id,
        "marked": saved.marked_for_review, "expires_in": expires_in,
    })


@roles(Role.STUDENT)
def attempt_remaining(request, pk):
    attempt = get_object_or_404(Attempt.objects.select_related("exam"), pk=pk, student=request.user)
    attempt = close_if_expired(attempt)
    return JsonResponse({"remaining_seconds": remaining_seconds(attempt)})


@roles(Role.STUDENT)
@require_POST
def save_answer(request, pk):
    """FR-019: save a response as it is selected. An empty option clears it; marked_for_review is "1" or "0"."""
    attempt = get_object_or_404(Attempt, pk=pk, student=request.user)
    question = request.POST.get("question", "")
    option = request.POST.get("option", "")
    flag = request.POST.get("marked_for_review")

    if not question.isdigit() or not (option == "" or option.isdigit()) or flag not in (None, "0", "1"):
        return JsonResponse(
            {"detail": "A question is required, with an option id or an empty option to clear it."},
            status=400,
        )

    try:
        services.save_answer(
            attempt, int(question), int(option) if option else None, None if flag is None else flag == "1"
        )
    except AttemptClosed as refusal:
        return JsonResponse({"detail": str(refusal)}, status=409)
    except (Question.DoesNotExist, Option.DoesNotExist):
        return JsonResponse(
            {"detail": "That option does not belong to this question."},
            status=400,
        )

    return JsonResponse({"saved": True})


@roles(Role.STUDENT)
@require_POST
def submit_attempt(request, pk):
    """Submit an attempt, or leave an already-expired attempt closed."""
    attempt = close_if_expired(
        get_object_or_404(Attempt, pk=pk, student=request.user)
    )
    services.submit(attempt)
    return redirect("attempt-paper", attempt.pk)
