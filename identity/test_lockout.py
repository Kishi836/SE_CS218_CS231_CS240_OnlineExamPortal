"""NFR-012 -- lock an account for 15 minutes after 5 failed sign-ins within 15 minutes.

SRS pass condition: the 6th sign-in attempt after 5 failures is refused even with the right password,
and succeeds after 15 minutes.
"""
from datetime import timedelta

from django.db.models import F
from django.test import TestCase
from django.urls import reverse

from portal.testkit import PASSWORD, World
from repository.models import SignInFailure

LOCKED = "Too many failed sign-ins"


class LockoutTests(TestCase):
    def setUp(self):
        self.world = World(n_questions=1)
        self.email = self.world.stu_a.email

    def sign_in(self, password, email=None):
        return self.client.post(reverse("login"), {"email": email or self.email, "password": password})

    def fail(self, times, email=None):
        for _ in range(times):
            self.sign_in("wrong-password", email)

    def age(self, minutes, rows=None):
        (rows or SignInFailure.objects.all()).update(at=F("at") - timedelta(minutes=minutes))

    def signed_in(self):
        return "_auth_user_id" in self.client.session

    def test_four_failures_then_right_password_signs_in(self):
        self.fail(4)
        self.assertEqual(self.sign_in(PASSWORD).status_code, 302)
        self.assertTrue(self.signed_in())

    def test_sixth_attempt_with_right_password_is_refused(self):
        self.fail(5)
        response = self.sign_in(PASSWORD)
        self.assertContains(response, LOCKED)
        self.assertFalse(self.signed_in())

    def test_lock_lifts_after_15_minutes(self):
        self.fail(5)
        self.age(16)
        self.assertEqual(self.sign_in(PASSWORD).status_code, 302)
        self.assertTrue(self.signed_in())

    def test_failures_older_than_15_minutes_do_not_count(self):
        self.fail(3)
        self.age(20)
        self.fail(2)
        self.sign_in(PASSWORD)
        self.assertTrue(self.signed_in())

    def test_unknown_email_is_counted_and_gives_the_same_message(self):
        self.fail(5, email="nobody@pesu.pes.edu")
        self.assertEqual(SignInFailure.objects.filter(email="nobody@pesu.pes.edu").count(), 5)
        self.assertContains(self.sign_in("anything", email="nobody@pesu.pes.edu"), LOCKED)

    def test_success_clears_the_count(self):
        self.fail(4)
        self.sign_in(PASSWORD)
        self.client.logout()
        self.fail(4)
        self.sign_in(PASSWORD)
        self.assertTrue(self.signed_in())

    def test_email_case_does_not_dodge_the_lock(self):
        self.fail(5, email=self.email.upper())
        self.assertContains(self.sign_in(PASSWORD), LOCKED)
