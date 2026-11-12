from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Max
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
def exam_submit(request, exam_id):
    """CR-02: Faculty sends a finished Draft to the Administrator, who schedules it. The paper is then locked."""
    exam = _faculty_exam_or_403(request, exam_id)

    if exam.status != Exam.Status.DRAFT:
        raise PermissionDenied("Only a Draft can be sent to the Administrator.")
    if exam.course.archived:
        raise PermissionDenied("This course is archived")
    if not ExamQuestion.objects.filter(exam=exam).exists():
        messages.error(request, "Add at least one question before sending the paper.")
        return redirect("exam-detail", exam_id=exam.pk)

    exam.status = Exam.Status.SUBMITTED
    exam.review_note = ""
    with transaction.atomic():
        exam.save(update_fields=["status", "review_note"])
        audit.record(request.user, "submit", exam, {"status": [Exam.Status.DRAFT, exam.status]})

    messages.success(request, "Paper sent to the Administrator for scheduling.")
    return redirect("exam-detail", exam_id=exam.pk)


@roles(Role.ADMIN)
@require_GET
def admin_exam_queue(request):
    """CR-02: papers waiting to be scheduled, and the ones already scheduled."""
    exams = Exam.objects.select_related("course").annotate(n_questions=Count("examquestion"))
    return render(request, "examsetup/admin_exam_queue.html", {
        "waiting": exams.filter(status=Exam.Status.SUBMITTED).order_by("id"),
        "scheduled": exams.filter(status=Exam.Status.PUBLISHED).order_by("-window_start"),
    })


@roles(Role.ADMIN)
@require_http_methods(["GET", "POST"])
def admin_exam_schedule(request, exam_id):
    """CR-02 / FR-012 / FR-013: the Administrator sets the window. Scheduling a paper Faculty sent publishes it."""
    exam = get_object_or_404(Exam.objects.select_related("course"), pk=exam_id)
    if exam.status == Exam.Status.DRAFT:
        raise PermissionDenied("Faculty has not sent this paper yet.")

    if request.method == "POST":
        old_status = exam.status
        form = ExamScheduleForm(request.POST, instance=exam)
        if form.is_valid():
            with transaction.atomic():
                exam = form.save(commit=False)
                if exam.status == Exam.Status.SUBMITTED:
                    exam.status = Exam.Status.PUBLISHED
                    exam.published_at = timezone.now()
                exam.save()
                audit.record(request.user, "schedule", exam, {
                    "status": [old_status, exam.status],
                    "window": [exam.window_start.isoformat(), exam.window_end.isoformat()],
                })
            messages.success(request, f"Examination scheduled: {exam.title}")
            return redirect("admin-exam-queue")
    else:
        form = ExamScheduleForm(instance=exam)

    questions = exam.examquestion_set.select_related("question").order_by("order")
    return render(request, "examsetup/exam_schedule.html", {"exam": exam, "form": form, "questions": questions})


@roles(Role.ADMIN)
@require_POST
def admin_exam_return(request, exam_id):
    """CR-02: the Administrator sends a paper back to Faculty as a Draft, with the reason."""
    exam = get_object_or_404(Exam, pk=exam_id, status=Exam.Status.SUBMITTED)
    note = request.POST.get("note", "").strip()
    if not note:
        messages.error(request, "Say what Faculty should change before returning the paper.")
        return redirect("admin-exam-schedule", exam_id=exam.pk)
    exam.status = Exam.Status.DRAFT
    exam.review_note = note[:2000]
    with transaction.atomic():
        exam.save(update_fields=["status", "review_note"])
        audit.record(request.user, "return", exam,
                     {"status": [Exam.Status.SUBMITTED, Exam.Status.DRAFT], "note": exam.review_note})
    messages.success(request, f"{exam.title} returned to Faculty.")
    return redirect("admin-exam-queue")
