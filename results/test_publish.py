"""FR-025 / FR-026 -- results are withheld until Faculty publishes, and can be unpublished
(Test Plan UT_059, UT_060, UT_061, IT_032, IT_033)."""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from portal.testkit import World, make_user
from repository.models import Role

from .services import ResultsNotReady, set_results_published


class PublishTests(TestCase):
    def setUp(self):
        self.world = World(n_questions=25)
        self.attempt = self.world.submitted(right=16, wrong=0)
        self.world.close_window()

    def as_student(self, student=None):
        self.client.force_login(student or self.world.stu_a)

    def publish(self, value):
        self.client.force_login(self.world.fac_a)
        return self.client.post(
            reverse("results-publish", args=[self.world.exam.pk]),
            {"publish": value},
        )

    def test_UT_059_unpublished_result_is_withheld(self):
        self.as_student()

        response = self.client.get(
            reverse("attempt-paper", args=[self.attempt.pk])
        )

        self.assertContains(response, "Results not yet published")
        self.assertNotContains(response, "32.00")
        self.assertNotContains(response, "64.00")
        self.assertNotContains(response, "Pass")

    def test_UT_060_publishing_makes_the_result_visible(self):
        self.publish("1")
        self.as_student()

        response = self.client.get(
            reverse("attempt-paper", args=[self.attempt.pk])
        )

        self.assertContains(response, "32.00")
        self.assertContains(response, "64.00")
        self.assertContains(response, "Pass")

    def test_UT_061_unpublishing_withdraws_it_and_keeps_the_score(self):
        self.publish("1")
        self.publish("0")
        self.as_student()

        response = self.client.get(
            reverse("attempt-paper", args=[self.attempt.pk])
        )

        self.assertContains(response, "Results not yet published")

        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.score, Decimal("32"))

    def test_IT_032_unpublished_result_is_403_through_the_api(self):
        self.as_student()

        response = self.client.get(
            reverse("result-api", args=[self.attempt.pk])
        )

        self.assertEqual(response.status_code, 403)
        self.assertNotContains(response, "32", status_code=403)

    def test_IT_033_another_students_result_is_403(self):
        other = self.world.submitted(self.world.stu_b, right=5)
        set_results_published(self.world.exam, True)
        self.as_student()

        response = self.client.get(
            reverse("result-api", args=[other.pk])
        )

        self.assertEqual(response.status_code, 403)
        self.assertNotContains(response, "10.00", status_code=403)

        own_response = self.client.get(
            reverse("result-api", args=[self.attempt.pk])
        )

        self.assertEqual(own_response.status_code, 200)
        self.assertEqual(own_response.json()["score"], "32.00")

    def test_publishing_before_the_window_closes_is_refused(self):
        exam = self.world.exam
        exam.window_end = timezone.now() + timezone.timedelta(hours=1)
        exam.results_published = False
        exam.save(update_fields=["window_end", "results_published"])

        with self.assertRaises(ResultsNotReady):
            set_results_published(exam, True)

        exam.refresh_from_db()
        self.assertFalse(exam.results_published)

    def test_only_the_courses_faculty_can_publish(self):
        other_faculty = make_user(
            Role.FACULTY,
            "other.fac@pes.edu",
        )
        self.client.force_login(other_faculty)

        response = self.client.post(
            reverse("results-publish", args=[self.world.exam.pk]),
            {"publish": "1"},
        )

        self.assertEqual(response.status_code, 403)
