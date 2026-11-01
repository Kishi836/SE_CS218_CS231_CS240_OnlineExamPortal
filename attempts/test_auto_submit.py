"""FR-020 -- automatic submission when the time runs out (Test Plan UC-10)."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from repository.models import Answer, Attempt, Course, Exam, ExamQuestion, Option, Question, Role, User

TIME_IS_UP = "Time is up. Your paper has been submitted."
ALREADY_SUBMITTED = "This attempt has already been submitted"


class AutoSubmitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.faculty = User.objects.create_user("fac.a@pes.edu", "Passw0rd!A", full_name="Fac A", role=Role.FACULTY)
        cls.student = User.objects.create_user("stu.a@pesu.pes.edu", "Passw0rd!A", full_name="Stu A", role=Role.STUDENT)
        cls.course = Course.objects.create(code="CRS_X", title="DBMS", semester=5)
        cls.course.students.add(cls.student)
        now = timezone.now()
        cls.exam = Exam.objects.create(
            course=cls.course, title="EXM_1", duration_minutes=3, total_marks=10, pass_mark_percent=40,
            status=Exam.Status.PUBLISHED, window_start=now - timedelta(hours=1), window_end=now + timedelta(hours=1),
        )
        cls.options = []  # (wrong, right) per question, +2 / -0.5
        for i in range(5):
            q = Question.objects.create(
                course=cls.course, stem=f"Stem number {i}", topic="t", difficulty=Question.Difficulty.EASY,
                positive_marks=2, negative_marks=Decimal("0.5"), created_by=cls.faculty,
            )
            ExamQuestion.objects.create(exam=cls.exam, question=q, order=i)
            cls.options.append((Option.objects.create(question=q, text="A"), Option.objects.create(question=q, text="B", is_correct=True)))

    def setUp(self):
        self.client.force_login(self.student)
        self.client.post("/api/attempts", {"exam": self.exam.pk})
        self.attempt = Attempt.objects.get()

    def elapse(self, seconds):
        """Move the attempt's server-stamped start back, as if `seconds` had passed since it began."""
        Attempt.objects.filter(pk=self.attempt.pk).update(started_at=self.attempt.started_at - timedelta(seconds=seconds))
        self.attempt.refresh_from_db()

    def run_out(self):
        self.elapse(3 * 60 + 1)

    def answer(self, option, **extra):
        return self.client.post(f"/api/attempts/{self.attempt.pk}/answers", {"question": option.question_id, "option": option.pk, **extra})

    def test_UT_049_the_paper_submits_itself_at_zero(self):
        self.elapse(3 * 60 - 30)
        self.assertContains(self.client.get(f"/attempts/{self.attempt.pk}/", follow=True), 'data-expires-in="30"')  # the page reloads itself then
        self.answer(self.options[0][1])
        self.elapse(31)
        self.assertContains(self.client.get(f"/attempts/{self.attempt.pk}/"), TIME_IS_UP)
        self.attempt.refresh_from_db()
        self.assertIsNotNone(self.attempt.submitted_at)

    def test_UT_050_every_response_saved_before_expiry_is_kept(self):
        for wrong, right in self.options[:3]:
            self.assertEqual(self.answer(right).status_code, 200)
        self.run_out()
        self.client.get(f"/attempts/{self.attempt.pk}/")
        self.assertEqual(Answer.objects.filter(attempt=self.attempt, option__isnull=False).count(), 3)

    def test_UT_051_no_response_is_accepted_after_auto_submission(self):
        self.answer(self.options[0][1])
        self.run_out()
        self.client.get(f"/attempts/{self.attempt.pk}/")
        response = self.answer(self.options[0][0])
        self.assertContains(response, ALREADY_SUBMITTED, status_code=409)
        self.assertEqual(Answer.objects.get(attempt=self.attempt).option, self.options[0][1])
        self.assertNotContains(self.client.get(f"/attempts/{self.attempt.pk}/"), 'type="radio"')

    def test_UT_052_submitted_at_is_the_start_plus_the_duration(self):
        self.run_out()
        self.client.get(f"/attempts/{self.attempt.pk}/")
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.submitted_at, self.attempt.started_at + timedelta(minutes=3))

    def test_IT_026_expiry_does_not_need_the_browser_open(self):
        self.answer(self.options[0][1])
        self.answer(self.options[1][1])
        self.run_out()  # no request at all while the time runs out
        self.client.logout()
        self.client.force_login(self.student)
        refused = self.client.post("/api/attempts", {"exam": self.exam.pk})
        self.assertContains(refused, "You have already submitted this examination", status_code=403)
        self.attempt.refresh_from_db()
        self.assertIsNotNone(self.attempt.submitted_at)
        self.assertEqual(self.attempt.answers.count(), 2)

    def test_IT_027_a_client_clock_cannot_defer_expiry(self):
        self.run_out()
        response = self.answer(self.options[0][1], client_time=(timezone.now() - timedelta(hours=1)).isoformat())
        self.assertContains(response, ALREADY_SUBMITTED, status_code=409)
        self.assertFalse(Answer.objects.exists())

    def test_IT_028_an_auto_submitted_attempt_is_evaluated(self):
        self.answer(self.options[0][1])  # +2
        self.answer(self.options[1][0])  # -0.5
        self.run_out()
        self.client.get(f"/attempts/{self.attempt.pk}/")
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.score, Decimal("1.5"))

    def test_ST_010_three_minute_paper_end_to_end(self):
        for wrong, right in self.options[:3]:
            self.answer(right)
        self.run_out()
        self.assertContains(self.client.get(f"/attempts/{self.attempt.pk}/"), TIME_IS_UP)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.answers.count(), 3)  # the other two have no Answer row: unattempted
        self.assertEqual(self.attempt.score, Decimal("6"))

    def test_manual_submit_is_scored_and_cannot_be_repeated(self):
        self.answer(self.options[0][1])
        self.assertRedirects(self.client.post(f"/attempts/{self.attempt.pk}/submit"), f"/attempts/{self.attempt.pk}/")
        self.attempt.refresh_from_db()
        first = self.attempt.submitted_at
        self.assertLess(first, self.attempt.started_at + timedelta(minutes=3))
        self.assertEqual(self.attempt.score, Decimal("2"))
        self.assertContains(self.client.get(f"/attempts/{self.attempt.pk}/"), "Your paper has been submitted.")
        self.client.post(f"/attempts/{self.attempt.pk}/submit")
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.submitted_at, first)

    def test_changing_an_answer_keeps_one_row(self):
        self.answer(self.options[0][0])
        self.answer(self.options[0][1])
        self.assertEqual(Answer.objects.get(attempt=self.attempt).option, self.options[0][1])

    def test_option_from_another_question_is_rejected(self):
        response = self.client.post(
            f"/api/attempts/{self.attempt.pk}/answers", {"question": self.options[0][0].question_id, "option": self.options[1][1].pk}
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Answer.objects.exists())

    def test_another_students_attempt_is_not_found(self):
        other = User.objects.create_user("stu.b@pesu.pes.edu", "Passw0rd!A", full_name="Stu B", role=Role.STUDENT)
        self.client.force_login(other)
        self.assertEqual(self.answer(self.options[0][1]).status_code, 404)
        self.assertEqual(self.client.post(f"/attempts/{self.attempt.pk}/submit").status_code, 404)
