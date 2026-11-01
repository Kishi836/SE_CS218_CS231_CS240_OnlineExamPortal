"""System tests for sitting an exam end to end (Test Plan ST_008: FR-015 - FR-018; ST_009: FR-019, FR-021)."""
from datetime import timedelta
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from repository.models import Answer, Attempt, Course, Exam, ExamQuestion, Option, Question, Role, User


class AttemptFlowTests(TestCase):
    """STU_A enrolled in a live 60-minute EXM_1 of 25 two-mark questions; option A is right."""

    def setUp(self):
        self.student = User.objects.create_user(
            "stu.a@pesu.pes.edu", "Passw0rd!A", full_name="Stu A", role=Role.STUDENT, roll_number="PES1UG24CS001"
        )
        faculty = User.objects.create_user("fac.a@pes.edu", "Passw0rd!A", full_name="Fac A", role=Role.FACULTY)
        course = Course.objects.create(code="CRS_X", title="DBMS", semester=5)
        course.students.add(self.student)
        now = timezone.now()
        self.exam = Exam.objects.create(
            course=course, title="EXM_1", duration_minutes=60, total_marks=Decimal("50"),
            pass_mark_percent=Decimal("40"), status=Exam.Status.PUBLISHED,
            window_start=now - timedelta(minutes=10), window_end=now + timedelta(minutes=50),
        )
        self.questions = []
        for i in range(25):
            q = Question.objects.create(
                course=course, stem=f"Stem number {i + 1}.", topic="t", difficulty=Question.Difficulty.EASY,
                positive_marks=2, created_by=faculty,
            )
            ExamQuestion.objects.create(exam=self.exam, question=q, order=i)
            q.opts = {letter: Option.objects.create(question=q, text=f"{letter}{i}", is_correct=letter == "A")
                      for letter in "ABCD"}
            self.questions.append(q)
        self.attempt = Attempt.objects.create(exam=self.exam, student=self.student)
        self.client.force_login(self.student)

    def page(self, n, client=None):
        return (client or self.client).get(reverse("attempt-question", args=[self.attempt.pk, n]))

    def post(self, n, letter=""):
        q = self.questions[n - 1]
        return self.client.post(
            reverse("attempt-answer", args=[self.attempt.pk]),
            {"question": q.pk, "option": q.opts[letter].pk if letter else ""},
        )

    def states(self, response):
        return [state for _, state in response.context["cells"]]

    def test_ST_008_paper_delivery_under_a_live_window(self):
        self.attempt.delete()
        start = reverse("attempt-start")
        Exam.objects.filter(pk=self.exam.pk).update(window_start=timezone.now() + timedelta(minutes=5))
        self.assertContains(self.client.post(start, {"exam": self.exam.pk}), "not opened yet", status_code=403)
        Exam.objects.filter(pk=self.exam.pk).update(window_start=timezone.now() - timedelta(seconds=1))
        response = self.client.post(start, {"exam": self.exam.pk}, follow=True)
        self.attempt = response.context["attempt"]
        self.assertAlmostEqual(response.context["expires_in"], 60 * 60, delta=5)
        for n in (2, 7, 25):  # palette links
            self.assertContains(response, f'href="{reverse("attempt-question", args=[self.attempt.pk, n])}"')
            self.assertContains(self.page(n), f"Stem number {n}.")
        self.post(7, "A")
        self.assertEqual(
            self.states(self.page(1))[:7], ["not-answered"] * 2 + ["not-visited"] * 4 + ["answered"]
        )
        self.client.post(reverse("attempt-submit", args=[self.attempt.pk]))
        paper = self.client.get(reverse("attempt-paper", args=[self.attempt.pk]))
        self.assertContains(paper, "Your paper has been submitted.")

    def test_ST_009_answer_change_clear_resume_and_submit(self):
        for n, letter in enumerate("ABCDA", 1):
            self.post(n, letter)
        self.post(2, "A")  # change two
        self.post(3, "A")
        self.post(5, "")   # clear one
        resumed = Client()
        resumed.force_login(self.student)
        response = resumed.post(reverse("attempt-start"), {"exam": self.exam.pk}, follow=True)
        self.assertEqual(response.context["attempt"], self.attempt)
        self.assertEqual(self.states(response)[:5], ["answered"] * 4 + ["not-answered"])
        for n in range(6, 26):
            self.post(n, "A")
        self.client.post(reverse("attempt-submit", args=[self.attempt.pk]))
        self.attempt.refresh_from_db()
        # Q1-Q3 correct (A), Q4 wrong (D), Q5 cleared, Q6-Q25 correct: 23 x 2 marks, no deduction set.
        self.assertEqual(self.attempt.score, Decimal("46"))
        self.assertEqual(Answer.objects.filter(attempt=self.attempt).count(), 25)
