"""FR-009 -- questions in use are versioned, never edited in place or deleted (Test Plan IT_013, IT_014, ST_005)."""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from repository.models import Answer, Attempt, Course, Exam, ExamQuestion, Option, Question, Role, User


def edit_data(question, stem, options=(("1NF", False), ("3NF", True))):
    data = {
        "stem": stem, "topic": question.topic, "difficulty": question.difficulty,
        "positive_marks": question.positive_marks, "negative_marks": question.negative_marks,
        "options-TOTAL_FORMS": "6", "options-INITIAL_FORMS": "0",
        "options-MIN_NUM_FORMS": "0", "options-MAX_NUM_FORMS": "6",
    }
    for i, (text, correct) in enumerate(options):
        data[f"options-{i}-text"] = text
        if correct:
            data[f"options-{i}-is_correct"] = "on"
    return data


class VersioningTests(TestCase):
    def setUp(self):
        self.faculty = User.objects.create_user("fac.a@pes.edu", "Passw0rd!A", full_name="Fac A", role=Role.FACULTY)
        self.student = User.objects.create_user(
            "stu.a@pesu.pes.edu", "Passw0rd!A", full_name="Stu A", role=Role.STUDENT, roll_number="PES1UG24CS001"
        )
        self.course = Course.objects.create(code="CRS_X", title="Course X", semester=5)
        self.course.faculty.add(self.faculty)
        self.q = Question.objects.create(
            course=self.course, stem="Which normal form removes transitive dependency?", topic="Normalization",
            difficulty=Question.Difficulty.MEDIUM, positive_marks=Decimal("2"), negative_marks=Decimal("0.5"),
            created_by=self.faculty,
        )
        Option.objects.create(question=self.q, text="1NF")
        self.right = Option.objects.create(question=self.q, text="3NF", is_correct=True)
        self.exam = Exam.objects.create(
            course=self.course, title="EXM_1", duration_minutes=30, total_marks=Decimal("2"),
            pass_mark_percent=Decimal("40"),
        )
        ExamQuestion.objects.create(exam=self.exam, question=self.q, order=0)
        self.client.force_login(self.faculty)

    def publish(self):
        Exam.objects.filter(pk=self.exam.pk).update(status=Exam.Status.PUBLISHED, published_at=timezone.now())

    def edit(self, question, stem, **kwargs):
        return self.client.post(reverse("question-edit", args=[question.pk]), edit_data(question, stem, **kwargs))

    def test_IT_013_published_question_is_versioned_not_edited(self):
        self.publish()
        before = Question.objects.filter(pk=self.q.pk).values().get()
        self.edit(self.q, "Which normal form removes transitive dependencies?")

        self.assertEqual(Question.objects.filter(pk=self.q.pk).values().exclude(retired=True).count(), 0)
        after = Question.objects.filter(pk=self.q.pk).values().get()
        self.assertEqual({**after, "retired": False}, before)  # only the retired flag moved
        v2 = Question.objects.get(previous=self.q)
        self.assertEqual((v2.version, v2.stem), (2, "Which normal form removes transitive dependencies?"))
        self.assertEqual(list(self.exam.questions.all()), [self.q])  # the paper still holds version 1
        self.assertEqual(list(self.q.options.values_list("text", "is_correct")), [("1NF", False), ("3NF", True)])

    def test_FR_009_unused_question_is_edited_in_place(self):
        self.edit(self.q, "New stem", options=(("A", True), ("B", False), ("C", False)))
        self.q.refresh_from_db()
        self.assertEqual((self.q.stem, self.q.version, Question.objects.count()), ("New stem", 1, 1))
        self.assertEqual(self.q.options.count(), 3)

    def test_FR_009_draft_exam_follows_the_new_version_when_another_exam_froze_it(self):
        published = Exam.objects.create(
            course=self.course, title="Published", duration_minutes=30, total_marks=Decimal("2"),
            pass_mark_percent=Decimal("40"), status=Exam.Status.PUBLISHED,
        )
        ExamQuestion.objects.create(exam=published, question=self.q, order=0)
        self.edit(self.q, "Edited")
        v2 = Question.objects.get(previous=self.q)
        self.assertEqual(list(self.exam.questions.all()), [v2])  # the draft moved on
        self.assertEqual(list(published.questions.all()), [self.q])  # the published paper did not

    def test_IT_014_answered_question_cannot_be_deleted(self):
        self.publish()
        attempt = Attempt.objects.create(exam=self.exam, student=self.student, submitted_at=timezone.now())
        Answer.objects.create(attempt=attempt, question=self.q, option=self.right)
        response = self.client.post(reverse("question-delete", args=[self.q.pk]), follow=True)
        self.assertContains(response, "This question has been attempted and cannot be deleted")
        self.assertTrue(Question.objects.filter(pk=self.q.pk).exists())
        self.assertEqual(Answer.objects.get().question.stem, "Which normal form removes transitive dependency?")

    def test_FR_009_unused_question_can_be_deleted(self):
        self.client.post(reverse("question-delete", args=[self.q.pk]))
        self.assertFalse(Question.objects.exists())

    def test_FR_009_superseded_version_is_hidden_from_the_bank(self):
        self.publish()
        self.edit(self.q, "v2 stem")
        response = self.client.get(reverse("question-list"))
        self.assertContains(response, "v2 stem")
        self.assertNotContains(response, "Which normal form removes transitive dependency?")
        self.assertEqual(self.client.get(reverse("question-edit", args=[self.q.pk])).status_code, 404)

    def test_ST_005_author_tag_publish_then_edits_become_versions(self):
        for i, topic in enumerate(["Joins", "Joins", "Indexing"]):
            self.client.post(reverse("question-create"), {
                **edit_data(self.q, f"Q{i}"), "course": self.course.pk, "topic": topic,
                "difficulty": ["EASY", "HARD", "EASY"][i],
            })
        new = list(Question.objects.filter(stem__in=["Q0", "Q1", "Q2"]).order_by("stem"))
        self.assertEqual([q.topic for q in new], ["Joins", "Joins", "Indexing"])
        exam = Exam.objects.create(
            course=self.course, title="ST_005", duration_minutes=30, total_marks=Decimal("6"),
            pass_mark_percent=Decimal("40"),
        )
        for i, q in enumerate(new):
            ExamQuestion.objects.create(exam=exam, question=q, order=i)
        self.client.post(reverse("exam-publish", args=[exam.pk]))
        exam.refresh_from_db()
        self.assertEqual(exam.status, Exam.Status.PUBLISHED)

        self.edit(new[0], "Q0 edited")
        self.assertEqual(list(exam.questions.values_list("stem", flat=True)), ["Q0", "Q1", "Q2"])
        self.assertTrue(Question.objects.filter(stem="Q0 edited", version=2).exists())
