"""The Student's exam page offers only the action that applies, and a published result links its scorecard (FR-014, FR-027)."""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from portal.testkit import World
from repository.models import Exam


class ExamActionTests(TestCase):
    def setUp(self):
        self.world = World()
        self.detail = reverse("student-exam-detail", args=[self.world.exam.pk])
        self.client.force_login(self.world.stu_a)

    def page(self):
        return self.client.get(self.detail).content.decode()

    def test_live_offers_start(self):
        self.assertIn("Start exam", self.page())

    def test_started_offers_resume(self):
        self.world.attempt(self.world.stu_a)
        self.assertIn("Resume exam", self.page())

    def test_upcoming_and_closed_offer_no_start(self):
        now = timezone.now()
        Exam.objects.filter(pk=self.world.exam.pk).update(window_start=now + timedelta(hours=1), window_end=now + timedelta(hours=2))
        html = self.page()
        self.assertIn("Opens at", html)
        self.assertNotIn("Start exam", html)
        self.world.close_window()
        html = self.page()
        self.assertIn("closed at", html)
        self.assertNotIn("Start exam", html)

    def test_submitted_links_scorecard_only_once_published(self):
        attempt = self.world.submitted(self.world.stu_a, right=1)
        scorecard = reverse("scorecard", args=[attempt.pk])
        self.assertIn("Results not yet published", self.page())
        self.assertNotIn(scorecard, self.client.get(reverse("student-dashboard")).content.decode())
        Exam.objects.filter(pk=self.world.exam.pk).update(results_published=True)
        self.assertIn(scorecard, self.page())
        self.assertIn(scorecard, self.client.get(reverse("student-dashboard")).content.decode())
