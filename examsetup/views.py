from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from identity.access import roles
from repository import audit
from repository.models import Exam, ExamQuestion, Role

from .forms import ExamForm, ExamQuestionForm, ExamScheduleForm


def _faculty_exam_or_403(request, exam_id):
    exam = get_object_or_404(
        Exam.objects.select_related("course"), pk=exam_id
    )
    if not exam.course.faculty.filter(pk=request.user.pk).exists():
        raise PermissionDenied("You are not assigned to this course.")
    return exam


@roles(Role.FACULTY)
@require_GET
def exam_list(request):
    exams = (
        Exam.objects.filter(course__faculty=request.user)
        .select_related("course")
        .order_by("-id")
    )
    return render(
        request, "examsetup/exam_list.html", {"exams": exams}
    )


@roles(Role.FACULTY)
def exam_create(request):
    if request.method == "POST":
        form = ExamForm(request.POST, user=request.user)
        if form.is_valid():
            exam = form.save(commit=False)
            if exam.course.archived:
                form.add_error("course", "This course is archived")
            else:
                exam.status = Exam.Status.DRAFT
                exam.published_at = None

                with transaction.atomic():
                    exam.save()
                    audit.record(request.user, "create", exam)

                messages.success(request, "Exam created as Draft.")
                return redirect("exam-detail", exam_id=exam.pk)
    else:
        form = ExamForm(user=request.user)

    return render(
        request,
        "examsetup/exam_form.html",
        {"form": form, "heading": "Create exam"},
    )


@roles(Role.FACULTY)
def exam_edit(request, exam_id):
    exam = _faculty_exam_or_403(request, exam_id)

    if exam.status != Exam.Status.DRAFT:
        raise PermissionDenied("Only Draft exams can be edited.")

    if request.method == "POST":
        # FR-030: capture every editable field BEFORE binding the form (attname, so the course is its id).
        fields = [Exam._meta.get_field(f).attname for f in ExamForm.Meta.fields]
        before = {f: getattr(exam, f) for f in fields}

        form = ExamForm(
            request.POST,
            instance=exam,
            user=request.user,
        )

        if form.is_valid():
            updated = form.save(commit=False)

            if updated.course.archived:
                form.add_error("course", "This course is archived")
            else:
                with transaction.atomic():
                    updated.save()

                    changes = {
                        f: [before[f], getattr(updated, f)]
                        for f in fields
                        if before[f] != getattr(updated, f)
                    }

                    if changes:
                        audit.record(
                            request.user,
                            "update",
                            updated,
                            changes,
                        )

                messages.success(request, "Draft exam updated.")
                return redirect("exam-detail", exam_id=exam.pk)
    else:
        form = ExamForm(instance=exam, user=request.user)

    return render(
        request,
        "examsetup/exam_form.html",
        {"form": form, "heading": "Edit draft exam"},
    )


@roles(Role.FACULTY)
@require_GET
def exam_detail(request, exam_id):
    exam = _faculty_exam_or_403(request, exam_id)
    exam_questions = (
        exam.examquestion_set.select_related("question")
        .order_by("order")
    )
    return render(
        request,
        "examsetup/exam_detail.html",
        {"exam": exam, "exam_questions": exam_questions},
    )


@roles(Role.FACULTY)
def exam_add_questions(request, exam_id):
    exam = _faculty_exam_or_403(request, exam_id)

    if exam.status != Exam.Status.DRAFT:
        raise PermissionDenied(
            "Only Draft exams can have questions added."
        )
    if exam.course.archived:
        raise PermissionDenied("This course is archived")

    if request.method == "POST":
        form = ExamQuestionForm(request.POST, exam=exam)
        if form.is_valid():
            max_order = (
                ExamQuestion.objects.filter(exam=exam)
                .aggregate(max_order=Max("order"))["max_order"]
            )
            next_order = 0 if max_order is None else max_order + 1

            for question in form.cleaned_data["questions"]:
                ExamQuestion.objects.create(
                    exam=exam,
                    question=question,
                    order=next_order,
                )
                next_order += 1

            messages.success(request, "Questions added.")
            return redirect("exam-detail", exam_id=exam.pk)
    else:
        form = ExamQuestionForm(exam=exam)

    return render(
        request,
        "examsetup/exam_questions.html",
        {"form": form, "exam": exam},
    )


@roles(Role.FACULTY)
@require_POST
def exam_publish(request, exam_id):
    exam = _faculty_exam_or_403(request, exam_id)

    if exam.status != Exam.Status.DRAFT:
        raise PermissionDenied(
            "Only Draft exams can be published."
        )
    if exam.course.archived:
        raise PermissionDenied("This course is archived")
    if not ExamQuestion.objects.filter(exam=exam).exists():
        messages.error(
            request, "Add at least one question before publishing."
        )
        return redirect("exam-detail", exam_id=exam.pk)

    old_status = exam.status
    exam.status = Exam.Status.PUBLISHED
    exam.published_at = timezone.now()

    with transaction.atomic():
        exam.save(update_fields=["status", "published_at"])
        audit.record(
            request.user,
            "publish",
            exam,
            {"status": [old_status, exam.status]},
        )

    messages.success(request, "Exam published.")
    return redirect("exam-detail", exam_id=exam.pk)


@roles(Role.FACULTY)
@require_http_methods(["GET", "POST"])
def exam_schedule(request, exam_id):
    exam = _faculty_exam_or_403(request, exam_id)
    if exam.status != Exam.Status.PUBLISHED:
        raise PermissionDenied("Only Published exams can be scheduled.")

    if request.method == "POST":
        form = ExamScheduleForm(request.POST, instance=exam)
        if form.is_valid():
            with transaction.atomic():
                updated = form.save()
                audit.record(request.user, "schedule", updated)

            messages.success(request, "Examination scheduled")
            return redirect("exam-detail", exam_id=exam.pk)
    else:
        form = ExamScheduleForm(instance=exam)

    return render(
        request,
        "examsetup/exam_schedule.html",
        {"exam": exam, "form": form},
    )
