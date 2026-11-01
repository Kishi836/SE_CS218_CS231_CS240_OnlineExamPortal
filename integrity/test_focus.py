"""FR-028 -- focus-loss events with a server timestamp (Test Plan UT_064, UT_065, UT_066, UT_067).

The browser half (focus.js firing once per switch) is checked by hand in Chrome / Edge / Firefox;
these tests cover the server half: one POST is one event, the time is the server's, nothing else is trusted.
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from portal.testkit import World, make_user
from repository.models import FocusEvent, Role
from attempts.services import submit


class FocusTests(TestCase):
    def setUp(self):
        self.world = World()
        self.attempt = self.world.attempt()
        self.client.force_login(self.world.stu_a)
        self.url = reverse("attempt-focus-lost", args=[self.attempt.pk])

    def test_UT_064_one_focus_loss_is_one_event_with_a_server_time(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 204)
        event = FocusEvent.objects.get(attempt=self.attempt)
        self.assertLess(abs((timezone.now() - event.occurred_at).total_seconds()), 5)

    def test_UT_065_three_losses_are_three_events(self):
        for _ in range(3): self.client.post(self.url)
        events = list(FocusEvent.objects.filter(attempt=self.attempt).order_by("occurred_at"))
        self.assertEqual(len(events), 3)
        self.assertEqual(events, sorted(events, key=lambda event: event.occurred_at))

    def test_UT_066_no_loss_means_no_event(self):
        self.client.get(reverse("attempt-paper", args=[self.attempt.pk]))
        q = self.world.questions[0]
        self.client.post(
            reverse("attempt-answer", args=[self.attempt.pk]),
            {"question": q.pk, "option": self.world.right[0].pk},
        )
        self.assertFalse(FocusEvent.objects.filter(attempt=self.attempt).exists())

    def test_UT_067_client_supplied_time_is_ignored(self):
        fake = (timezone.now() + timedelta(hours=1)).isoformat()
        self.client.post(self.url, {"occurred_at": fake, "at": fake}, HTTP_DATE=fake)
        self.assertLess(abs((timezone.now() - FocusEvent.objects.get().occurred_at).total_seconds()), 5)

    def test_submitted_attempt_refuses_new_events(self):
        submit(self.attempt)
        self.assertEqual(self.client.post(self.url).status_code, 409)
        self.assertFalse(FocusEvent.objects.exists())

    def test_another_students_attempt_is_404(self):
        self.client.force_login(self.world.stu_b)
        self.assertEqual(self.client.post(self.url).status_code, 404)
        self.assertFalse(FocusEvent.objects.exists())

    def test_faculty_integrity_page_lists_each_attempts_events(self):
        self.client.post(self.url); self.client.post(self.url)
        self.client.force_login(self.world.fac_a)
        response = self.client.get(reverse("exam-integrity", args=[self.world.exam.pk]))
        self.assertContains(response, self.world.stu_a.full_name)
        self.assertContains(response, "<td>2</td>")
        other_faculty = make_user(Role.FACULTY, "fac.other@pes.edu")
        self.client.force_login(other_faculty)
        self.assertEqual(self.client.get(reverse("exam-integrity", args=[self.world.exam.pk])).status_code, 403)
        self.client.force_login(self.world.stu_a)
        self.assertEqual(self.client.get(reverse("exam-integrity", args=[self.world.exam.pk])).status_code, 403)
