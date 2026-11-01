"""FR-010 - FR-012: paper assembly and publication (Test Plan UT_032, UT_033, IT_015, IT_016, ST_006)."""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from repository.models import AuditEntry, Course, Exam, Option, Question, Role, User


class PublicationTests(TestCase):
    """FAC_A, STU_A (enrolled), STU_B (not), CRS_X and a bank of ten 2-mark questions."""

    def setUp(self):
        self.faculty = User.objects.create_user("fac.a@pes.edu", "Passw0rd!A", full_name="Fac A", role=Role.FACULTY)
        self.stu_a = User.objects.create_user(
            "stu.a@pesu.pes.edu", "Passw0rd!A", full_name="Stu A", role=Role.STUDENT, roll_number="PES1UG24CS001"
        )
        self.stu_b = User.objects.create_user(
            "stu.b@pesu.pes.edu", "Passw0rd!A", full_name="Stu B", role=Role.STUDENT, roll_number="PES1UG24CS002"
        )
        self.course = Course.objects.create(code="CRS_X", title="Course X", semester=5)
        self.course.faculty.add(self.faculty)
        self.course.students.add(self.stu_a)
        self.bank = []
        for i in range(10):
            q = Question.objects.create(
                course=self.course, stem=f"Bank Q{i}", topic="t", difficulty=Question.Difficulty.EASY,
                positive_marks=Decimal("2"), created_by=self.faculty,
            )
            Option.objects.create(question=q, text="A", is_correct=True)
            Option.objects.create(question=q, text="B")
            self.bank.append(q)

    def create_exam_with(self, questions):
        self.client.force_login(self.faculty)
        self.client.post(reverse("exam-create"), {
            "title": "EXM_1", "course": self.course.pk, "duration_minutes": "30",
            "total_marks": str(2 * len(questions)), "instructions": "Answer all.", "negative_marking": "on",
            "shuffle_options": "on", "pass_mark_percent": "40",
        })
        exam = Exam.objects.latest("id")
        self.client.post(reverse("exam-add-questions", args=[exam.pk]), {"questions": [q.pk for q in questions]})
        return exam

    def publish(self, exam):
        self.client.force_login(self.faculty)
        return self.client.post(reverse("exam-publish", args=[exam.pk]))

    def test_UT_032_draft_exam_is_invisible_to_students(self):
        exam = self.create_exam_with(self.bank[:5])
        self.client.force_login(self.stu_a)
        self.assertNotContains(self.client.get(reverse("student-exam-list")), "EXM_1")
        self.assertIn(self.client.get(reverse("student-exam-detail", args=[exam.pk])).status_code, (403, 404))

    def test_UT_033_publishing_moves_the_exam_out_of_draft_with_a_server_timestamp(self):
        exam = self.create_exam_with(self.bank[:5])
        before = timezone.now()
        self.publish(exam)
        exam.refresh_from_db()
        self.assertEqual(exam.status, Exam.Status.PUBLISHED)
        self.assertGreaterEqual(exam.published_at, before)
        self.assertTrue(AuditEntry.objects.filter(entity="Exam", entity_id=exam.pk, action="publish",
                                                  actor=self.faculty).exists())  # FR-030

    def test_IT_015_exactly_the_selected_questions_attach_in_the_chosen_order(self):
        chosen = [self.bank[7], self.bank[2], self.bank[9], self.bank[0], self.bank[4]]
        exam = self.create_exam_with(chosen)
        self.assertEqual(list(exam.questions.order_by("examquestion__order")), chosen)

    def test_IT_016_published_exam_is_visible_to_enrolled_students_only(self):
        exam = self.create_exam_with(self.bank[:5])
        self.publish(exam)
        self.client.force_login(self.stu_a)
        self.assertContains(self.client.get(reverse("student-exam-list")), "EXM_1")
        self.client.force_login(self.stu_b)
        self.assertNotContains(self.client.get(reverse("student-exam-list")), "EXM_1")
        self.assertEqual(self.client.get(reverse("student-exam-detail", args=[exam.pk])).status_code, 403)

    def test_ST_006_paper_assembly_and_publication_keep_the_policy_values(self):
        exam = self.create_exam_with(self.bank[:5])
        self.client.force_login(self.stu_a)
        self.assertNotContains(self.client.get(reverse("student-exam-list")), "EXM_1")
        self.publish(exam)
        self.client.force_login(self.stu_a)
        self.assertContains(self.client.get(reverse("student-exam-list")), "EXM_1")
        exam.refresh_from_db()
        self.assertEqual(
            (exam.duration_minutes, exam.total_marks, exam.negative_marking, exam.shuffle_questions,
             exam.shuffle_options, exam.pass_mark_percent),
            (30, Decimal("10"), True, False, True, Decimal("40")),
        )
