"""System test ST_007 -- an exam moves Upcoming -> Live -> Completed on the Student dashboard (FR-013, FR-014)."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from attempts.services import dashboard_groups
from repository.models import Attempt, Course, Exam, Role, User

START = "Start exam"


class DashboardFlowTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            "stu.a@pesu.pes.edu", "Passw0rd!A", full_name="Stu A", role=Role.STUDENT, roll_number="PES1UG24CS001"
        )
        self.course = Course.objects.create(code="UE24CS341A", title="Software Engineering", semester=5)
        self.course.students.add(self.student)
        self.client.force_login(self.student)

    def group_of(self, exam):
        return next(name for name, exams in dashboard_groups(self.student).items() if exam in exams)

    def test_ST_007_exam_moves_upcoming_live_completed_as_server_time_advances(self):
        now = timezone.now()
        exam = Exam.objects.create(
            course=self.course, title="EXM_1", duration_minutes=30, total_marks=Decimal("50"),
            pass_mark_percent=Decimal("40"), status=Exam.Status.PUBLISHED,
            window_start=now + timedelta(minutes=2), window_end=now + timedelta(minutes=62),
        )
        self.assertEqual(self.group_of(exam), "upcoming")
        Exam.objects.filter(pk=exam.pk).update(window_start=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.group_of(exam), "live")
        self.client.post(reverse("attempt-start"), {"exam": exam.pk})
        attempt = Attempt.objects.get(exam=exam, student=self.student)
        self.client.post(reverse("attempt-submit", args=[attempt.pk]))
        self.assertEqual(self.group_of(exam), "completed")
        self.assertNotContains(self.client.get(reverse("student-dashboard")), START)
