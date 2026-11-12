"""FR-013: scheduling (Test Plan UT_034, UT_035, IT_017). CR-02: the Administrator schedules a paper Faculty sent."""
from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from repository.models import Course, Exam, Role, User


def make_user(role, email, password="Passw0rd!A", **extra):
    return User.objects.create_user(email, password, full_name=email, role=role, **extra)


class ExamSchedulingTests(TestCase):
    def setUp(self):
        self.admin = make_user(Role.ADMIN, "adm.a@pes.edu")
        self.faculty = make_user(Role.FACULTY, "fac.a@pes.edu")
        self.course = Course.objects.create(code="UE24CS351A", title="Database Management Systems", semester=5)
        self.course.faculty.add(self.faculty)
        self.exam = Exam.objects.create(
            course=self.course,
            title="DBMS Unit Test 1",
            duration_minutes=60,
            total_marks=Decimal("50"),
            pass_mark_percent=Decimal("40"),
            status=Exam.Status.SUBMITTED,
        )

    def schedule_data(self, start="2026-09-10T10:00", end="2026-09-10T12:00"):
        return {"window_start": start, "window_end": end}

    def test_UT_034_sent_exam_window_is_saved_and_shown(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("admin-exam-schedule", args=[self.exam.pk]),
            self.schedule_data(),
            follow=True,
        )
        self.exam.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Examination scheduled")
        self.assertContains(response, "2026-09-10 10:00 IST")
        self.assertIsNotNone(self.exam.window_start)
        self.assertIsNotNone(self.exam.window_end)

    def test_UT_035_window_end_must_be_later_than_start(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("admin-exam-schedule", args=[self.exam.pk]),
            self.schedule_data(start="2026-09-10T12:00", end="2026-09-10T10:00"),
        )
        self.exam.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The window end must be later than the window start")
        self.assertIsNone(self.exam.window_start)
        self.assertIsNone(self.exam.window_end)
        self.assertEqual(self.exam.status, Exam.Status.SUBMITTED)  # an invalid window publishes nothing

    def test_IT_017_schedule_is_stored_as_aware_utc_time(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("admin-exam-schedule", args=[self.exam.pk]), self.schedule_data())
        self.exam.refresh_from_db()
        expected_start = datetime(2026, 9, 10, 4, 30, tzinfo=datetime_timezone.utc)
        self.assertTrue(self.exam.window_start.tzinfo is not None)
        self.assertEqual(self.exam.window_start, expected_start)

    def test_draft_exam_cannot_be_scheduled(self):
        self.exam.status = Exam.Status.DRAFT
        self.exam.save(update_fields=["status"])
        self.client.force_login(self.admin)
        response = self.client.post(reverse("admin-exam-schedule", args=[self.exam.pk]), self.schedule_data())
        self.assertEqual(response.status_code, 403)

    def test_faculty_cannot_schedule(self):
        self.client.force_login(self.faculty)
        response = self.client.get(reverse("admin-exam-schedule", args=[self.exam.pk]))
        self.assertEqual(response.status_code, 403)

    def test_published_exam_window_can_be_moved_by_the_administrator(self):
        self.exam.status = Exam.Status.PUBLISHED
        self.exam.save(update_fields=["status"])
        self.client.force_login(self.admin)
        self.client.post(reverse("admin-exam-schedule", args=[self.exam.pk]), self.schedule_data())
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.status, Exam.Status.PUBLISHED)
        self.assertIsNotNone(self.exam.window_start)
