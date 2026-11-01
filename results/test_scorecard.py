"""FR-027 -- the Student scorecard with per-question marks (Test Plan UT_062, UT_063, IT_034, ST_012)."""
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from portal.testkit import World, make_user
from repository.models import Exam, Role

from .services import scorecard


class ScorecardTests(TestCase):
    def setUp(self):
        self.world = World(n_questions=25)
        # 17 right, 4 wrong, 4 unanswered: 34 - 2 = 32 of 50 -> 64%, Pass at 40% (the Test Plan's figures).
        self.attempt = self.world.submitted(right=17, wrong=4)
        Exam.objects.filter(pk=self.world.exam.pk).update(results_published=True)
        self.attempt.refresh_from_db()
        self.client.force_login(self.world.stu_a)

    def test_figures_match_the_test_plan(self):
        self.assertEqual((self.attempt.score, self.attempt.percentage, self.attempt.passed), (Decimal("32"), Decimal("64"), True))

    def test_UT_062_scorecard_shows_total_percentage_outcome_and_every_question(self):
        response = self.client.get(reverse("scorecard", args=[self.attempt.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "32.00")
        self.assertContains(response, "64.00")
        self.assertContains(response, "Pass")
        self.assertEqual(len(response.context["card"]["rows"]), 25)
        self.assertContains(response, "-0.50")
        self.assertContains(response, "0")
        self.assertContains(response, "Not answered")

    def test_UT_063_per_question_marks_sum_to_the_total(self):
        card = scorecard(self.attempt)
        self.assertEqual(sum(row["marks"] for row in card["rows"]), card["score"])

    def test_ST_012_end_to_end_publication_and_scorecard(self):
        Exam.objects.filter(pk=self.world.exam.pk).update(results_published=False)
        self.assertEqual(self.client.get(reverse("scorecard", args=[self.attempt.pk])).status_code, 403)

        Exam.objects.filter(pk=self.world.exam.pk).update(results_published=True)
        response = self.client.get(reverse("scorecard", args=[self.attempt.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "32.00")
        self.assertContains(response, "64.00")
        self.assertContains(response, "Pass")

        Exam.objects.filter(pk=self.world.exam.pk).update(results_published=False)
        self.assertEqual(self.client.get(reverse("scorecard", args=[self.attempt.pk])).status_code, 403)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.score, Decimal("32"))

    def test_IT_034_every_published_scorecard_matches_the_stored_evaluation(self):
        students = [self.world.stu_a, self.world.stu_b]
        for i in range(3, 6):
            s = make_user(Role.STUDENT, f"stu.{i}@pesu.pes.edu", roll_number=f"PES1UG24CS00{i}")
            self.world.course.students.add(s)
            students.append(s)

        mixes = [(17, 4), (20, 0), (5, 10), (0, 0), (10, 0)]
        for student, (right, wrong) in zip(students, mixes):
            attempt = self.attempt if student == self.world.stu_a else self.world.submitted(student=student, right=right, wrong=wrong)
            c = Client()
            c.force_login(student)
            response = c.get(reverse("scorecard", args=[attempt.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, f"{attempt.score:.2f}")
            self.assertContains(response, f"{attempt.percentage:.2f}")
            self.assertContains(response, "Pass" if attempt.passed else "Fail")

    def test_unpublished_scorecard_is_403(self):
        Exam.objects.filter(pk=self.world.exam.pk).update(results_published=False)
        self.assertEqual(self.client.get(reverse("scorecard", args=[self.attempt.pk])).status_code, 403)

    def test_another_students_scorecard_is_403(self):
        self.client.force_login(self.world.stu_b)
        self.assertEqual(self.client.get(reverse("scorecard", args=[self.attempt.pk])).status_code, 403)

    def test_scorecard_never_reveals_the_correct_option(self):
        response = self.client.get(reverse("scorecard", args=[self.attempt.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "is_correct")
        self.assertNotContains(response, "Correct")
        for row in response.context["card"]["rows"][17:21]:
            self.assertEqual(row["chosen"], "B")
            self.assertNotEqual(row["chosen"], "A")
