from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_POST

from attempts.services import dashboard_groups
from repository.forms import CourseForm, EnrollmentForm
from repository.models import Course, Role, User

from .access import public, roles
from .forms import RegistrationForm


@public
@sensitive_post_parameters("password1", "password2")
def register(request):
    """Create a Student account without ever accepting a role from the browser."""
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                form.save()
        except IntegrityError as error:
            # Validation handles normal duplicates. This is the race-condition fallback.
            message = str(error).lower()
            if "roll_number" in message:
                form.add_error("roll_number", "This roll number is already registered")
            else:
                form.add_error("email", "An account with this email already exists")
        else:
            messages.success(request, "Registration successful")
            return redirect("login")
    return render(request, "registration/register.html", {"form": form})


@roles(*Role.values)
def home(request):
    return redirect(f"{request.user.role.lower()}-dashboard")


@roles(Role.STUDENT)
def student_dashboard(request):
    """FR-014: the tiles plus the Student's exams grouped as Upcoming / Live / Completed."""
    return render(request, "identity/dashboard.html", {"groups": dashboard_groups(request.user)})


# Placeholder dashboards so each role has a landing page; the real ones are the consoles.


@roles(Role.FACULTY)
def faculty_dashboard(request):
    return render(request, "identity/dashboard.html")


@roles(Role.ADMIN)
def admin_dashboard(request):
    return render(request, "identity/dashboard.html")


@roles(Role.ADMIN)
@require_GET
def course_list(request):
    courses = Course.objects.prefetch_related("faculty", "students").order_by(
        "semester", "code"
    )
    return render(request, "identity/course_list.html", {"courses": courses})


@roles(Role.ADMIN)
def course_create(request):
    if request.method == "POST":
        form = CourseForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Course created successfully.")
            return redirect("course-list")
    else:
        form = CourseForm()

    return render(
        request,
        "identity/course_form.html",
        {"form": form, "heading": "Create course"},
    )


@roles(Role.ADMIN)
def course_edit(request, course_id):
    course = get_object_or_404(Course, pk=course_id)

    if request.method == "POST":
        form = CourseForm(request.POST, instance=course)
        if form.is_valid():
            form.save()
            messages.success(request, "Course updated successfully.")
            return redirect("course-list")
    else:
        form = CourseForm(instance=course)

    return render(
        request,
        "identity/course_form.html",
        {"form": form, "heading": "Edit course"},
    )


@roles(Role.ADMIN)
@require_POST
def course_archive(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    course.archived = True
    course.save(update_fields=["archived"])
    messages.success(request, "Course archived successfully.")
    return redirect("course-list")


@roles(Role.FACULTY)
@require_GET
def faculty_courses(request):
    courses = Course.objects.filter(
        faculty=request.user
    ).prefetch_related("students").order_by("semester", "code")
    return render(
        request, "identity/faculty_courses.html", {"courses": courses}
    )


@roles(Role.FACULTY, Role.ADMIN)
@require_GET
def course_roster(request, course_id):
    course = get_object_or_404(Course, pk=course_id)

    if (
        request.user.role != Role.ADMIN
        and not course.faculty.filter(pk=request.user.pk).exists()
    ):
        raise PermissionDenied("You are not assigned to this course.")

    students = course.students.filter(role=Role.STUDENT).order_by("full_name")
    return render(
        request,
        "identity/course_roster.html",
        {"course": course, "students": students},
    )


@roles(Role.ADMIN)
@require_POST
def student_erase(request, student_id):
    """NFR-008: an Administrator erases a Student's personal data on request (DPDP Act, within 30 days)."""
    student = get_object_or_404(User, pk=student_id, role=Role.STUDENT)  # Faculty / Admin ids -> 404
    from .erasure import erase_student
    erase_student(student)
    messages.success(request, "Personal data erased.")
    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}):
        return redirect(next_url)
    return redirect("course-list")


@roles(Role.FACULTY, Role.ADMIN)
def course_enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)

    if (
        request.user.role != Role.ADMIN
        and not course.faculty.filter(pk=request.user.pk).exists()
    ):
        raise PermissionDenied("You are not assigned to this course.")

    if course.archived:
        messages.error(request, "This course is archived")
        return redirect("course-roster", course_id=course.pk)

    if request.method == "POST":
        form = EnrollmentForm(request.POST)
        if form.is_valid():
            student = form.cleaned_data["student"]
            if course.students.filter(pk=student.pk).exists():
                form.add_error("student", "This student is already enrolled")
            else:
                course.students.add(student)
                messages.success(request, "Student enrolled successfully.")
                return redirect("course-roster", course_id=course.pk)
    else:
        form = EnrollmentForm()

    return render(
        request,
        "identity/enrollment_form.html",
        {"form": form, "course": course},
    )


@roles(Role.FACULTY, Role.ADMIN)
@require_POST
def course_unenroll(request, course_id, student_id):
    course = get_object_or_404(Course, pk=course_id)

    if (
        request.user.role != Role.ADMIN
        and not course.faculty.filter(pk=request.user.pk).exists()
    ):
        raise PermissionDenied("You are not assigned to this course.")

    student = get_object_or_404(User, pk=student_id, role=Role.STUDENT)
    if course.students.filter(pk=student.pk).exists():
        course.students.remove(student)
        messages.success(request, "Student unenrolled successfully.")

    return redirect("course-roster", course_id=course.pk)
