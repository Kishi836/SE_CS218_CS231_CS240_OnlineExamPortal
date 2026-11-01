"""FR-030 -- the mutations the review of PR 96 found unaudited: question edits (with the answer key),
submission and evaluation, every changed exam field, and results publication."""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from portal.testkit import World
from questionbank.test_versioning import edit_data
from repository.models import AuditEntry, Exam, Option, Question


class AuditCoverageTests(TestCase):
    def setUp(self):
        self.world = World()

    def entry(self, **filters):
        return AuditEntry.objects.get(**filters)

    def test_UT_068_question_edit_records_old_and_new_stem_and_answer_key(self):
        q = Question.objects.create(
            course=self.world.course, stem="Old stem", topic="t", difficulty=Question.Difficulty.EASY,
            positive_marks=Decimal("2"), created_by=self.world.fac_a,
        )
        Option.objects.create(question=q, text="1NF", is_correct=True)
        Option.objects.create(question=q, text="3NF")
        self.client.force_login(self.world.fac_a)
        self.client.post(reverse("question-edit", args=[q.pk]),
                         edit_data(q, "New stem", options=(("1NF", False), ("3NF", True))))
        changes = self.entry(entity="Question", entity_id=q.pk, action="update", actor=self.world.fac_a).changes
        self.assertEqual(changes["stem"], ["Old stem", "New stem"])
        self.assertEqual(changes["options"], [
            [{"text": "1NF", "is_correct": True}, {"text": "3NF", "is_correct": False}],
            [{"text": "1NF", "is_correct": False}, {"text": "3NF", "is_correct": True}],
        ])

    def test_question_in_use_records_a_version_entry(self):
        q = self.world.questions[0]  # on the published EXM_1, so the edit becomes version 2
        self.client.force_login(self.world.fac_a)
        self.client.post(reverse("question-edit", args=[q.pk]), edit_data(q, "Reworded"))
        new = Question.objects.get(previous=q)
        changes = self.entry(entity="Question", entity_id=new.pk, action="version").changes
        self.assertEqual(changes["previous_version"], q.pk)

    def test_submit_is_the_students_and_evaluation_the_systems(self):
        attempt = self.world.attempt()
        self.client.force_login(self.world.stu_a)
        self.client.post(reverse("attempt-submit", args=[attempt.pk]))
        self.entry(entity="Attempt", entity_id=attempt.pk, action="submit", actor=self.world.stu_a)
        evaluated = self.entry(entity="Attempt", entity_id=attempt.pk, action="evaluate")
        self.assertIsNone(evaluated.actor)
        self.assertEqual(evaluated.changes["score"], [None, "0"])

    def test_exam_edit_records_every_changed_field(self):
        exam = self.world.exam
        Exam.objects.filter(pk=exam.pk).update(status=Exam.Status.DRAFT)
        self.client.force_login(self.world.fac_a)
        self.client.post(reverse("exam-edit", args=[exam.pk]), {
            "title": exam.title, "course": exam.course_id, "duration_minutes": 45,
            "total_marks": exam.total_marks, "instructions": "", "pass_mark_percent": "50",
        })
        changes = self.entry(entity="Exam", entity_id=exam.pk, action="update").changes
        self.assertEqual(changes["duration_minutes"], [exam.duration_minutes, 45])
        self.assertIn("pass_mark_percent", changes)
        self.assertNotIn("title", changes)

    def test_results_publication_is_audited(self):
        self.world.close_window()
        self.client.force_login(self.world.fac_a)
        self.client.post(reverse("results-publish", args=[self.world.exam.pk]), {"publish": "1"})
        changes = self.entry(entity="Exam", action="publish_results", actor=self.world.fac_a).changes
        self.assertEqual(changes["results_published"], [False, True])
