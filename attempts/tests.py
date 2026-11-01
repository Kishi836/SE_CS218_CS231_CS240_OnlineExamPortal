
"""Tests for starting attempts and delivering the exam paper."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from repository.models import (
    Attempt,
    Course,
    Exam,
    ExamQuestion,
    Option,
    Question,
    Role,
    User,
)


class StartAttemptTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.faculty = User.objects.create_user(
            "fac.a@pes.edu",
            "Passw0rd!A",
            full_name="Fac A",
            role=Role.FACULTY,
        )
        cls.student = User.objects.create_user(
            "stu.a@pesu.pes.edu",
            "Passw0rd!A",
            full_name="Stu A",
            role=Role.STUDENT,
        )
        cls.course = Course.objects.create(
            code="CRS_X",
            title="DBMS",
            semester=5,
        )
        cls.course.students.add(cls.student)

        now = timezone.now()
        cls.exam = Exam.objects.create(
            course=cls.course,
            title="DBMS Unit Test 1",
            duration_minutes=60,
            total_marks=4,
            pass_mark_percent=40,
            status=Exam.Status.PUBLISHED,
            window_start=now - timedelta(minutes=10),
            window_end=now + timedelta(minutes=50),
        )

        for i in range(2):
            question = Question.objects.create(
                course=cls.course,
                stem=f"Stem number {i}",
                topic="t",
                difficulty=Question.Difficulty.EASY,
                positive_marks=2,
                created_by=cls.faculty,
            )
            ExamQuestion.objects.create(
                exam=cls.exam,
                question=question,
                order=i,
            )
            Option.objects.create(question=question, text=f"Wrong {i}")
            Option.objects.create(
                question=question,
                text=f"Right {i}",
                is_correct=True,
            )

    def setUp(self):
        self.client.force_login(self.student)

    def start(self, **extra):
        return self.client.post("/api/attempts", {"exam": self.exam.pk, **extra})

    def set_window(self, start, end):
        Exam.objects.filter(pk=self.exam.pk).update(
            window_start=start,
            window_end=end,
        )

    def assertRefused(self, response, message):
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, message, status_code=403)
        self.assertNotContains(response, "Stem number", status_code=403)

    def test_UT_039_start_is_refused_before_the_window_opens(self):
        now = timezone.now()
        self.set_window(
            now + timedelta(minutes=10),
            now + timedelta(minutes=70),
        )
        self.assertRefused(self.start(), "This examination has not opened yet")
        self.assertFalse(Attempt.objects.exists())

    def test_UT_040_start_is_refused_after_the_window_closes(self):
        now = timezone.now()
        self.set_window(
            now - timedelta(minutes=61),
            now - timedelta(minutes=1),
        )
        self.assertRefused(self.start(), "This examination has closed")
        self.assertFalse(Attempt.objects.exists())

    def test_UT_041_start_is_refused_when_a_submitted_attempt_exists(self):
        Attempt.objects.create(
            exam=self.exam,
            student=self.student,
            submitted_at=timezone.now(),
        )
        self.assertRefused(
            self.start(),
            "You have already submitted this examination",
        )
        self.assertEqual(Attempt.objects.count(), 1)

    def test_IT_010_student_not_enrolled_is_refused(self):
        self.course.students.remove(self.student)
        self.assertEqual(self.start().status_code, 403)
        self.assertFalse(Attempt.objects.exists())

    def test_draft_exam_cannot_be_started(self):
        Exam.objects.filter(pk=self.exam.pk).update(status=Exam.Status.DRAFT)
        self.assertEqual(self.start().status_code, 403)
        self.assertFalse(Attempt.objects.exists())

    def test_unscheduled_exam_has_not_opened(self):
        self.set_window(None, None)
        self.assertRefused(
            self.start(),
            "This examination has not opened yet",
        )

    def test_IT_019_attempt_row_exists_before_the_paper_is_delivered(self):
        response = self.start()
        attempt = Attempt.objects.get(exam=self.exam, student=self.student)

        self.assertRedirects(response, f"/attempts/{attempt.pk}/", target_status_code=302)
        self.assertNotContains(response, "Stem number", status_code=302)

        paper = self.client.get(f"/attempts/{attempt.pk}/", follow=True)
        self.assertContains(paper, "Stem number 0")
        self.assertNotContains(paper, "Stem number 1")

    def test_IT_019_no_paper_without_an_attempt_row(self):
        self.assertEqual(self.client.get("/attempts/999/").status_code, 404)

    def test_IT_020_stored_start_time_is_the_servers(self):
        before = timezone.now()
        self.start(started_at="2030-01-01T00:00:00Z")
        after = timezone.now()

        started = Attempt.objects.get().started_at
        self.assertTrue(before <= started <= after)

    def test_starting_again_returns_the_same_attempt(self):
        self.start()
        self.start()
        self.assertEqual(Attempt.objects.count(), 1)

    def test_paper_never_carries_the_answer_key(self):
        self.start()
        paper = self.client.get(f"/attempts/{Attempt.objects.get().pk}/", follow=True)
        self.assertNotContains(paper, "is_correct")
        self.assertNotContains(paper, "correct")

    def test_another_students_paper_is_not_found(self):
        self.start()
        other = User.objects.create_user(
            "stu.b@pesu.pes.edu",
            "Passw0rd!A",
            full_name="Stu B",
            role=Role.STUDENT,
        )
        self.client.force_login(other)

        self.assertEqual(
            self.client.get(
                f"/attempts/{Attempt.objects.get().pk}/").status_code,
            404,
        )

    def test_faculty_cannot_start_an_attempt(self):
        self.client.force_login(self.faculty)
        self.assertEqual(self.start().status_code, 403)
