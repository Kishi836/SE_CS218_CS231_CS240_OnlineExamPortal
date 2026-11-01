"""FR-021 -- resuming an interrupted attempt (Test Plan UC-09)."""
from datetime import timedelta
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from repository.models import Attempt, Course, Exam, ExamQuestion, Option, Question, Role, User

from .services import save_answer


class ResumeTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            "stu.a@pesu.pes.edu", "Passw0rd!A", full_name="Stu A", role=Role.STUDENT, roll_number="PES1UG24CS001"
        )
        faculty = User.objects.create_user("fac.a@pes.edu", "Passw0rd!A", full_name="Fac A", role=Role.FACULTY)
        course = Course.objects.create(code="UE24CS341A", title="Software Engineering", semester=5)
        course.students.add(self.student)
        now = timezone.now()
        self.exam = Exam.objects.create(
            course=course, title="EXM_1", duration_minutes=60, total_marks=Decimal("12"),
            pass_mark_percent=Decimal("40"), status=Exam.Status.PUBLISHED,
            window_start=now - timedelta(hours=1), window_end=now + timedelta(hours=1),
        )
        self.options = []
        for i in range(6):
            q = Question.objects.create(
                course=course, stem=f"Q{i}", topic="t", difficulty=Question.Difficulty.EASY,
                positive_marks=2, created_by=faculty,
            )
            ExamQuestion.objects.create(exam=self.exam, question=q, order=i)
            self.options.append(Option.objects.create(question=q, text="A", is_correct=True))
            Option.objects.create(question=q, text="B")
        self.client.force_login(self.student)

    def started_minutes_ago(self, minutes, answered=0):
        attempt = Attempt.objects.create(exam=self.exam, student=self.student)
        Attempt.objects.filter(pk=attempt.pk).update(started_at=timezone.now() - timedelta(minutes=minutes))
        attempt.refresh_from_db()
        for option in self.options[:answered]:
            save_answer(attempt, option.question_id, option.pk)
        return attempt

    def resume(self, client=None):
        """Reopen the exam the way a Student does: the Start button on the exam page."""
        response = (client or self.client).post(reverse("attempt-start"), {"exam": self.exam.pk}, follow=True)
        self.assertEqual(response.status_code, 200)
        return response

    def assertRemainingAbout(self, response, minutes):
        self.assertAlmostEqual(response.context["expires_in"], minutes * 60, delta=5)

    def test_UT_048_remaining_time_on_resume_counts_from_the_original_start(self):
        self.started_minutes_ago(20)
        self.assertRemainingAbout(self.resume(), 40)

    def test_IT_024_resume_restores_answers_and_grants_no_extra_time(self):
        attempt = self.started_minutes_ago(25, answered=4)
        response = self.resume()
        self.assertEqual(response.context["attempt"], attempt)
        self.assertRemainingAbout(response, 35)
        saved = [
            self.client.get(reverse("attempt-question", args=[attempt.pk, n])).context["saved"]
            for n in range(1, 7)
        ]
        self.assertEqual(saved, [o.pk for o in self.options[:4]] + [None, None])

    def test_IT_025_another_device_resumes_the_same_attempt(self):
        attempt = self.started_minutes_ago(10, answered=3)
        other_device = Client()
        other_device.post(reverse("login"), {"email": "stu.a@pesu.pes.edu", "password": "Passw0rd!A"})
        response = self.resume(other_device)
        self.assertEqual(response.context["attempt"], attempt)
        saved_count = sum(
            other_device.get(reverse("attempt-question", args=[attempt.pk, n])).context["saved"] is not None
            for n in range(1, 7)
        )
        self.assertEqual(saved_count, 3)
        self.assertEqual(Attempt.objects.filter(exam=self.exam, student=self.student).count(), 1)

    def test_FR_021_resume_still_works_after_the_window_closes_if_time_remains(self):
        # Started 10 minutes before the window closed; 50 minutes of the attempt are left.
        self.started_minutes_ago(10, answered=2)
        Exam.objects.filter(pk=self.exam.pk).update(window_end=timezone.now() - timedelta(minutes=1))
        self.assertRemainingAbout(self.resume(), 50)

    def test_FR_021_a_new_attempt_is_still_refused_after_the_window_closes(self):
        Exam.objects.filter(pk=self.exam.pk).update(window_end=timezone.now() - timedelta(minutes=1))
        response = self.client.post(reverse("attempt-start"), {"exam": self.exam.pk})
        self.assertContains(response, "This examination has closed", status_code=403)
        self.assertFalse(Attempt.objects.exists())
