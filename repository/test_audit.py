"""FR-030 -- the append-only audit trail (Test Plan UT_068, IT_036, IT_037, ST_013)."""

from django.db import DatabaseError, connection, transaction
from django.test import TestCase
from django.urls import reverse

from portal.testkit import World
from repository.models import Course
from repository import audit
from repository.models import AppendOnly, AuditEntry, Exam


class AuditTests(TestCase):
    def setUp(self):
        self.world = World()

    def test_record_stores_actor_action_entity_time_and_changes(self):
        entry = audit.record(
            self.world.fac_a,
            "update",
            self.world.exam,
            {"title": ["EXM_1", "EXM_2"]},
        )

        self.assertEqual(
            (
                entry.actor,
                entry.action,
                entry.entity,
                entry.entity_id,
            ),
            (
                self.world.fac_a,
                "update",
                "Exam",
                self.world.exam.pk,
            ),
        )
        self.assertEqual(
            entry.changes,
            {"title": ["EXM_1", "EXM_2"]},
        )
        self.assertIsNotNone(entry.at)

    def test_UT_068_an_edit_records_old_and_new_values(self):
        exam = self.world.exam
        Exam.objects.filter(pk=exam.pk).update(
            status=Exam.Status.DRAFT
        )
        exam.refresh_from_db()

        self.client.force_login(self.world.fac_a)

        edit_url = reverse(
            "exam-edit",
            kwargs={"exam_id": exam.pk},
        )

        data = {
            "title": "EXM_2",
            "course": exam.course_id,
            "duration_minutes": exam.duration_minutes,
            "total_marks": exam.total_marks,
            "instructions": exam.instructions or "",
            "negative_marking": exam.negative_marking,
            "shuffle_questions": exam.shuffle_questions,
            "shuffle_options": exam.shuffle_options,
            "pass_mark_percent": exam.pass_mark_percent,
        }

        response = self.client.post(edit_url, data)

        if response.status_code == 200:
            # Expose form validation errors if the fixture or form has
            # additional requirements that need to be handled.
            form = response.context.get("form")
            self.fail(
                f"Exam edit returned HTTP 200 instead of redirecting. "
                f"Form errors: {form.errors.as_json() if form else 'No form found'}"
            )

        self.assertEqual(response.status_code, 302)

        entries = AuditEntry.objects.filter(
            entity="Exam",
            entity_id=exam.pk,
            action="update",
            actor=self.world.fac_a,
        )

        self.assertEqual(entries.count(), 1)
        self.assertEqual(
            entries.first().changes.get("title"),
            ["EXM_1", "EXM_2"],
        )

    def test_IT_036_every_mutation_class_writes_an_entry(self):
        import json

        from repository.models import Attempt, User

        # User: register through the real registration view.
        response = self.client.post(
            reverse("register"),
            {
                "full_name": "Audit Test Student",
                "email": "audit.test@pesu.pes.edu",
                "roll_number": "PES1UG24CS099",
                "password1": "Passw0rd!A",
                "password2": "Passw0rd!A",
                "consent": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        new_user = User.objects.get(email="audit.test@pesu.pes.edu")

        # Course: create through the Admin view.
        self.client.force_login(self.world.adm_a)
        response = self.client.post(
            reverse("course-create"),
            {
                "code": "AUDIT101",
                "title": "Audit Test Course",
                "semester": 6,
                "faculty": [str(self.world.fac_a.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)

        course = Course.objects.get(code="AUDIT101", semester=6)

        # Question: create through the Faculty API.
        self.client.force_login(self.world.fac_a)
        response = self.client.post(
            reverse("question-api"),
            data=json.dumps(
                {
                    "course": self.world.course.pk,
                    "stem": "Audit integration question",
                    "topic": "Testing",
                    "difficulty": "EASY",
                    "positive_marks": "2",
                    "negative_marks": "0.5",
                    "options": [
                        {"text": "Correct", "is_correct": True},
                        {"text": "Incorrect", "is_correct": False},
                    ],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)

        # Exam: create through the Faculty view.
        response = self.client.post(
            reverse("exam-create"),
            {
                "title": "Audit Integration Exam",
                "course": self.world.course.pk,
                "duration_minutes": 30,
                "total_marks": "10",
                "instructions": "",
                "pass_mark_percent": "40",
            },
        )
        self.assertEqual(response.status_code, 302)

        # Attempt: start and submit through the Student views.
        self.client.force_login(self.world.stu_a)
        response = self.client.post(
            reverse("attempt-start"),
            {"exam": self.world.exam.pk},
        )
        self.assertEqual(response.status_code, 302)

        attempt = Attempt.objects.get(
            exam=self.world.exam,
            student=self.world.stu_a,
        )

        response = self.client.post(
            reverse("attempt-submit", kwargs={"pk": attempt.pk})
        )
        self.assertEqual(response.status_code, 302)

        # Every required entity must have an audit entry.
        for entity in ("User", "Course", "Question", "Exam", "Attempt"):
            with self.subTest(entity=entity):
                self.assertTrue(
                    AuditEntry.objects.filter(entity=entity).exists(),
                    f"No audit entry recorded for {entity}",
                )

    def test_IT_037_audit_rows_cannot_be_changed_or_deleted(self):
        entry = audit.record(None, "create", self.world.exam)

        with self.assertRaises(AppendOnly):
            entry.action = "tampered"
            entry.save()

        with self.assertRaises(AppendOnly):
            entry.delete()

        with self.assertRaises(AppendOnly):
            AuditEntry.objects.filter(pk=entry.pk).update(
                action="tampered"
            )

        with self.assertRaises(AppendOnly):
            AuditEntry.objects.all().delete()

        with (
            self.assertRaises(DatabaseError),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "UPDATE repository_auditentry SET action = 'tampered'"
            )

        with (
            self.assertRaises(DatabaseError),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute("DELETE FROM repository_auditentry")

        self.assertEqual(
            AuditEntry.objects.get(pk=entry.pk).action,
            "create",
        )

    def test_ST_013_admin_reads_the_log_filtered_to_one_exam(self):
        audit.record(self.world.fac_a, "publish", self.world.exam)
        audit.record(self.world.fac_a, "create", self.world.course)

        self.client.force_login(self.world.adm_a)

        response = self.client.get(
            reverse("audit-log"),
            {
                "entity": "Exam",
                "entity_id": self.world.exam.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "publish")
        self.assertNotContains(response, "Course #")

        self.client.force_login(self.world.fac_a)
        response = self.client.get(reverse("audit-log"))
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.world.stu_a)
        response = self.client.get(reverse("audit-log"))
        self.assertEqual(response.status_code, 403)
