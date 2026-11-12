
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from repository.models import (
    Course,
    Exam,
    ExamQuestion,
    Option,
    Question,
    Role,
    User,
)


class ExamAuthoringTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.faculty = User.objects.create_user(
            email="faculty@example.com",
            password="testpass123",
            full_name="Test Faculty",
            role=Role.FACULTY,
        )
        cls.other_faculty = User.objects.create_user(
            email="other@example.com",
            password="testpass123",
            full_name="Other Faculty",
            role=Role.FACULTY,
        )
        cls.student = User.objects.create_user(
            email="student@example.com",
            password="testpass123",
            full_name="Test Student",
            role=Role.STUDENT,
            roll_number="S001",
        )

        cls.course = Course.objects.create(
            code="CS101",
            title="Computer Science",
            semester=3,
        )
        cls.course.faculty.add(cls.faculty)

        cls.other_course = Course.objects.create(
            code="CS102",
            title="Other Course",
            semester=3,
        )
        cls.other_course.faculty.add(cls.faculty)

        cls.archived_course = Course.objects.create(
            code="CS103",
            title="Archived Course",
            semester=3,
            archived=True,
        )
        cls.archived_course.faculty.add(cls.faculty)

        cls.question1 = cls.make_question(
            cls.course, cls.faculty, "Question one"
        )
        cls.question2 = cls.make_question(
            cls.course, cls.faculty, "Question two"
        )
        cls.question3 = cls.make_question(
            cls.course, cls.faculty, "Question three"
        )
        cls.foreign_question = cls.make_question(
            cls.other_course, cls.faculty, "Foreign question"
        )

    @classmethod
    def make_question(cls, course, creator, stem):
        return Question.objects.create(
            course=course,
            stem=stem,
            topic="General",
            difficulty=Question.Difficulty.EASY,
            positive_marks=Decimal("1.00"),
            negative_marks=Decimal("0.50"),
            created_by=creator,
        )

    def create_exam(self, **overrides):
        values = {
            "course": self.course,
            "title": "Test Exam",
            "duration_minutes": 30,
            "total_marks": Decimal("10.00"),
            "instructions": "Read each question carefully.",
            "negative_marking": True,
            "shuffle_questions": False,
            "shuffle_options": False,
            "pass_mark_percent": Decimal("40.00"),
        }
        values.update(overrides)
        return Exam.objects.create(**values)

    def login_as_faculty(self):
        self.client.force_login(self.faculty)

    def test_UT_028_exam_defaults_to_draft(self):
        exam = self.create_exam()
        self.assertEqual(exam.status, Exam.Status.DRAFT)
        self.assertIsNone(exam.published_at)

    def test_UT_029_duration_must_be_positive(self):
        self.login_as_faculty()

        for duration in ("0", "-30"):
            with self.subTest(duration=duration):
                response = self.client.post(
                    reverse("exam-create"),
                    {
                        "title": "Invalid Duration Exam",
                        "course": self.course.pk,
                        "duration_minutes": duration,
                        "total_marks": "10",
                        "instructions": "",
                        "negative_marking": "on",
                        "pass_mark_percent": "40",
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response,
                    "Duration must be a positive number of minutes",
                )

    def test_UT_030_exam_policies_are_saved(self):
        exam = self.create_exam(
            negative_marking=False,
            shuffle_questions=True,
            shuffle_options=True,
            pass_mark_percent=Decimal("65.00"),
        )
        exam.refresh_from_db()

        self.assertFalse(exam.negative_marking)
        self.assertTrue(exam.shuffle_questions)
        self.assertTrue(exam.shuffle_options)
        self.assertEqual(exam.pass_mark_percent, Decimal("65.00"))

    def test_UT_031_pass_mark_must_be_between_zero_and_100(self):
        self.login_as_faculty()

        for pass_mark in ("150", "-10"):
            with self.subTest(pass_mark=pass_mark):
                response = self.client.post(
                    reverse("exam-create"),
                    {
                        "title": "Invalid Pass Mark Exam",
                        "course": self.course.pk,
                        "duration_minutes": "30",
                        "total_marks": "10",
                        "instructions": "",
                        "negative_marking": "on",
                        "pass_mark_percent": pass_mark,
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response,
                    "Pass mark must be between 0 and 100",
                )

    def test_archived_course_is_rejected_with_exact_message(self):
        self.login_as_faculty()

        response = self.client.post(
            reverse("exam-create"),
            {
                "title": "Archived Exam",
                "course": self.archived_course.pk,
                "duration_minutes": "30",
                "total_marks": "10",
                "instructions": "",
                "negative_marking": "on",
                "pass_mark_percent": "40",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This course is archived")
        self.assertFalse(Exam.objects.filter(title="Archived Exam").exists())

    def test_exam_creation_rejects_unassigned_course(self):
        self.login_as_faculty()
        unassigned = Course.objects.create(
            code="CS104",
            title="Unassigned",
            semester=3,
        )

        response = self.client.post(
            reverse("exam-create"),
            {
                "title": "Unauthorized Course Exam",
                "course": unassigned.pk,
                "duration_minutes": "30",
                "total_marks": "10",
                "instructions": "",
                "negative_marking": "on",
                "pass_mark_percent": "40",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Exam.objects.filter(title="Unauthorized Course Exam").exists()
        )

    def test_questions_are_attached_in_submitted_order(self):
        self.login_as_faculty()
        exam = self.create_exam()

        response = self.client.post(
            reverse("exam-add-questions", args=[exam.pk]),
            {
                "questions": [
                    str(self.question3.pk),
                    str(self.question1.pk),
                    str(self.question2.pk),
                ]
            },
        )

        self.assertRedirects(
            response, reverse("exam-detail", args=[exam.pk])
        )
        ordered_ids = list(
            ExamQuestion.objects.filter(exam=exam)
            .order_by("order")
            .values_list("question_id", flat=True)
        )
        self.assertEqual(
            ordered_ids,
            [
                self.question3.pk,
                self.question1.pk,
                self.question2.pk,
            ],
        )

    def test_cross_course_question_is_rejected(self):
        self.login_as_faculty()
        exam = self.create_exam()

        response = self.client.post(
            reverse("exam-add-questions", args=[exam.pk]),
            {"questions": [str(self.foreign_question.pk)]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            ExamQuestion.objects.filter(
                exam=exam, question=self.foreign_question
            ).exists()
        )

    def test_duplicate_question_is_rejected(self):
        self.login_as_faculty()
        exam = self.create_exam()
        ExamQuestion.objects.create(
            exam=exam, question=self.question1, order=0
        )

        response = self.client.post(
            reverse("exam-add-questions", args=[exam.pk]),
            {"questions": [str(self.question1.pk)]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            ExamQuestion.objects.filter(
                exam=exam, question=self.question1
            ).count(),
            1,
        )

    def test_send_to_admin_sets_status_without_publishing(self):
        self.login_as_faculty()
        exam = self.create_exam()
        ExamQuestion.objects.create(
            exam=exam, question=self.question1, order=0
        )

        response = self.client.post(
            reverse("exam-submit", args=[exam.pk])
        )

        self.assertRedirects(
            response, reverse("exam-detail", args=[exam.pk])
        )
        exam.refresh_from_db()
        self.assertEqual(exam.status, Exam.Status.SUBMITTED)
        self.assertIsNone(exam.published_at)  # CR-02: the Administrator's scheduling publishes it

    def test_sending_without_questions_is_blocked(self):
        self.login_as_faculty()
        exam = self.create_exam()

        self.client.post(reverse("exam-submit", args=[exam.pk]))
        exam.refresh_from_db()

        self.assertEqual(exam.status, Exam.Status.DRAFT)
        self.assertIsNone(exam.published_at)

    def test_other_faculty_cannot_access_exam(self):
        exam = self.create_exam()
        self.client.force_login(self.other_faculty)

        response = self.client.get(
            reverse("exam-detail", args=[exam.pk])
        )

        self.assertEqual(response.status_code, 403)

    def test_published_exam_cannot_be_edited(self):
        self.login_as_faculty()
        exam = self.create_exam(status=Exam.Status.PUBLISHED)

        response = self.client.get(
            reverse("exam-edit", args=[exam.pk])
        )

        self.assertEqual(response.status_code, 403)
