import logging

from django.contrib.messages import get_messages
from django.contrib.sessions.models import Session
from django.test import TestCase

from repository.models import Role, User


def make_user(role, email, password="Passw0rd!A", **extra):
    return User.objects.create_user(email, password, full_name=email, role=role, **extra)


class RegistrationTests(TestCase):
    registration_data = {
        "full_name": "Arjun Rao",
        "email": "arjun.rao@pesu.pes.edu",
        "roll_number": "PES1UG24CS111",
        "password1": "Str0ng#Pass",
        "password2": "Str0ng#Pass",
        "consent": "on",
    }

    def register(self, **changes):
        data = {**self.registration_data, **changes}
        return self.client.post("/register/", data, follow=True)

    def test_UT_001_register_with_all_fields_valid(self):
        response = self.register()
        user = User.objects.get(email=self.registration_data["email"])
        self.assertEqual(user.role, Role.STUDENT)
        self.assertContains(response, "Registration successful")

    def test_UT_002_roll_number_is_required(self):
        response = self.register(roll_number="")
        self.assertContains(response, "Roll number is required")
        self.assertFalse(User.objects.filter(email=self.registration_data["email"]).exists())

    def test_UT_003_non_institutional_email_is_rejected(self):
        response = self.register(email="arjun.rao@gmail.com")
        self.assertContains(response, "Please register with your institutional email address")

    def test_UT_004_invalid_email_is_rejected(self):
        response = self.register(email="arjun.rao.pesu.pes.edu")
        self.assertContains(response, "Enter a valid email address")

    def test_UT_005_duplicate_email_is_rejected(self):
        existing = make_user(Role.STUDENT, "stu.a@pesu.pes.edu", roll_number="PES1UG24CS001")
        response = self.register(email=existing.email, roll_number="PES1UG24CS999")
        self.assertContains(response, "An account with this email already exists")
        self.assertEqual(User.objects.get(pk=existing.pk).roll_number, "PES1UG24CS001")

    def test_UT_006_duplicate_roll_number_is_rejected(self):
        make_user(Role.STUDENT, "stu.a@pesu.pes.edu", roll_number="PES1UG24CS001")
        response = self.register(roll_number="PES1UG24CS001")
        self.assertContains(response, "This roll number is already registered")

    def test_IT_001_registration_stores_a_hash_not_the_password(self):
        self.register()
        user = User.objects.get(email=self.registration_data["email"])
        self.assertTrue(user.password.startswith("pbkdf2_sha256$"))
        self.assertNotEqual(user.password, self.registration_data["password1"])

    def test_IT_002_duplicate_roll_number_creates_only_one_account(self):
        self.register(email="one@pesu.pes.edu", roll_number="PES1UG24CS222")
        response = self.register(email="two@pesu.pes.edu", roll_number="PES1UG24CS222")
        self.assertContains(response, "This roll number is already registered")
        self.assertEqual(User.objects.filter(roll_number="PES1UG24CS222").count(), 1)


class SignInTests(TestCase):
    def setUp(self):
        self.student = make_user(
            Role.STUDENT, "stu.a@pesu.pes.edu", roll_number="PES1UG24CS001"
        )

    def sign_in(self, email="stu.a@pesu.pes.edu", password="Passw0rd!A", **extra):
        return self.client.post("/login/", {"email": email, "password": password, **extra})

    def test_ST_001_register_sign_in_and_load_student_dashboard(self):
        response = self.client.post("/register/", {
            "full_name": "Arjun Rao", "email": "arjun.rao@pesu.pes.edu",
            "roll_number": "PES1UG24CS111", "password1": "Str0ng#Pass", "password2": "Str0ng#Pass", "consent": "on",
        })
        self.assertRedirects(response, "/login/")
        response = self.sign_in("arjun.rao@pesu.pes.edu", "Str0ng#Pass", next="/student/")
        self.assertRedirects(response, "/student/")

    def test_UT_007_correct_credentials_establish_a_session(self):
        response = self.sign_in()
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_UT_008_wrong_password_is_refused(self):
        response = self.sign_in(password="WrongPass1")
        self.assertContains(response, "Invalid email or password")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_UT_009_unknown_email_has_the_same_message(self):
        response = self.sign_in(email="nobody@pesu.pes.edu", password="AnyPass123")
        self.assertContains(response, "Invalid email or password")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_UT_010_empty_password_is_refused(self):
        response = self.sign_in(password="")
        self.assertContains(response, "Password is required")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_IT_003_successful_login_rotates_the_session_key(self):
        self.client.get("/login/")
        before = self.client.session.session_key
        response = self.sign_in()
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertNotEqual(before, self.client.session.session_key)

    def test_NFR_011_passwords_are_hashed_and_not_logged(self):
        logger = logging.getLogger()
        with self.assertNoLogs(logger, level="WARNING"):
            response = self.sign_in()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.get(pk=self.student.pk).password.startswith("pbkdf2_sha256$"))
