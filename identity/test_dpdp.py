"""NFR-008 -- DPDP Act 2023: consent at registration, erasure on request.

SRS pass condition: registration cannot complete without ticking consent; an Administrator can erase
a Student's personal data.
"""
from django.test import TestCase
from django.urls import reverse

from portal.testkit import World
from repository.models import Attempt, User

from .erasure import NotAStudent, erase_student

FORM = {
    "full_name": "Stu C", "email": "stu.c@pesu.pes.edu", "roll_number": "PES1UG24CS003",
    "password1": "Passw0rd!A", "password2": "Passw0rd!A",
}


class ConsentTests(TestCase):
    def test_registration_without_consent_is_refused(self):
        response = self.client.post(reverse("register"), FORM)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You must consent to register")
        self.assertFalse(User.objects.filter(email=FORM["email"]).exists())

    def test_registration_with_consent_stores_when_it_was_given(self):
        response = self.client.post(reverse("register"), {**FORM, "consent": "on"})
        self.assertRedirects(response, reverse("login"))
        self.assertIsNotNone(User.objects.get(email=FORM["email"]).consent_given_at)


class ErasureTests(TestCase):
    def setUp(self):
        self.world = World(n_questions=2)
        self.attempt = self.world.submitted(right=1)

    def test_erasure_removes_personal_data_and_keeps_the_attempt(self):
        erase_student(self.world.stu_a)
        self.world.stu_a.refresh_from_db()
        self.assertEqual(self.world.stu_a.full_name, "Erased student")
        self.assertEqual(self.world.stu_a.email, f"erased-{self.world.stu_a.pk}@invalid.local")
        self.assertIsNone(self.world.stu_a.roll_number)
        self.assertFalse(self.client.login(email="stu.a@pesu.pes.edu", password="Passw0rd!A"))
        self.assertFalse(self.world.stu_a.is_active)
        self.assertTrue(Attempt.objects.filter(pk=self.attempt.pk).exists())

    def test_only_students_can_be_erased(self):
        with self.assertRaises(NotAStudent):
            erase_student(self.world.fac_a)

    def test_admin_erases_through_the_roster_button(self):
        self.client.force_login(self.world.adm_a)
        response = self.client.post(reverse("student-erase", args=[self.world.stu_a.pk]))
        self.assertEqual(response.status_code, 302)
        self.world.stu_a.refresh_from_db()
        self.assertTrue(self.world.stu_a.email.endswith("@invalid.local"))

    def test_faculty_and_students_cannot_erase(self):
        for user in (self.world.fac_a, self.world.stu_b):
            self.client.force_login(user)
            self.assertEqual(self.client.post(reverse("student-erase", args=[self.world.stu_a.pk])).status_code, 403)
        self.assertTrue(Attempt.objects.filter(pk=self.attempt.pk, student__email="stu.a@pesu.pes.edu").exists())
