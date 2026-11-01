"""FR-003, FR-005, FR-006 -- one role per account, and each Student sees only their own course's exams
(Test Plan UT_011, UT_021, ST_004)."""
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from portal.testkit import World, make_user
from repository.models import Course, Exam, Role, User


class CohortTests(TestCase):
    def setUp(self):
        self.world = World(n_questions=1)  # CRS_X with FAC_A, STU_A and STU_B enrolled, EXM_1 live
        self.world.course.students.remove(self.world.stu_b)
        self.fac_b = make_user(Role.FACULTY, "fac.b@pes.edu")
        self.crs_y = Course.objects.create(code="UE24CS352A", title="Machine Learning", semester=5)
        self.crs_y.faculty.add(self.fac_b)
        now = timezone.now()
        self.exm_y = Exam.objects.create(
            course=self.crs_y, title="EXM_Y", duration_minutes=30, total_marks=Decimal("2"),
            pass_mark_percent=Decimal("40"), status=Exam.Status.PUBLISHED, published_at=now,
            window_start=now - timedelta(hours=1), window_end=now + timedelta(hours=1),
        )

    def listed(self, student):
        self.client.force_login(student)
        dashboard = self.client.get(reverse("student-dashboard")).context["groups"]
        return {e.title for group in dashboard.values() for e in group}

    def test_UT_011_every_account_carries_exactly_one_valid_role(self):
        for user, role in ((self.world.stu_a, Role.STUDENT), (self.world.fac_a, Role.FACULTY), (self.world.adm_a, Role.ADMIN)):
            self.assertEqual(User.objects.get(pk=user.pk).role, role)
        for bad in ("", "STUDENT,FACULTY", "ROOT"):
            with self.assertRaises(IntegrityError), transaction.atomic():
                User.objects.filter(pk=self.world.stu_a.pk).update(role=bad)  # the database itself refuses

    def test_UT_021_student_sees_only_exams_of_enrolled_courses(self):
        self.assertEqual(self.listed(self.world.stu_a), {"EXM_1"})

    def test_ST_004_end_to_end_cohort_isolation_between_two_courses(self):
        self.world.course.students.remove(self.world.stu_a)
        self.client.force_login(self.world.fac_a)  # 1. FAC_A enrolls STU_A into CRS_X
        self.client.post(reverse("course-enroll", args=[self.world.course.pk]), {"student": self.world.stu_a.pk})
        self.client.force_login(self.fac_b)  # 2. FAC_B enrolls STU_B into CRS_Y
        self.client.post(reverse("course-enroll", args=[self.crs_y.pk]), {"student": self.world.stu_b.pk})
        self.assertEqual(self.listed(self.world.stu_a), {"EXM_1"})  # 3.
        self.assertEqual(self.listed(self.world.stu_b), {"EXM_Y"})  # 4.
        for student, other in ((self.world.stu_a, self.exm_y), (self.world.stu_b, self.world.exam)):  # 5.
            self.client.force_login(student)
            self.assertEqual(self.client.get(reverse("student-exam-detail", args=[other.pk])).status_code, 403)
            self.assertEqual(self.client.post(reverse("attempt-start"), {"exam": other.pk}).status_code, 403)
