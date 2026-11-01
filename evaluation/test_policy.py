"""NFR-010 -- examination policy values (window, pass mark, negative marking) are configurable per examination
and are not hard-coded.

SRS pass condition: code review finds no hard-coded pass mark or negative-marking value, and changing them
on an examination changes its scoring. The first is the source scan below; the second is every other test.
"""
import ast
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from attempts.services import save_answer, submit
from examsetup.forms import ExamForm, ExamScheduleForm
from portal.testkit import World
from questionbank.forms import QuestionForm
from repository.models import Exam, Question

# The scoring and attempt code: the only places a policy value could be baked in.
SCORING_CODE = ["evaluation/engine.py", "attempts/services.py", "attempts/views.py"]
# Numbers that are arithmetic, not policy: 0, 1, 100 (percent) and 0.01 (two-place rounding).
ALLOWED = {"0", "1", "100", "0.01"}


class PolicyTests(TestCase):
    def setUp(self):
        self.world = World(n_questions=10)  # +2 / -0.5, total 20

    def sit(self, right, wrong, student=None):
        """A fresh attempt with `right` correct and `wrong` incorrect answers, submitted and evaluated."""
        attempt = self.world.attempt(student)
        for option in self.world.right[:right] + self.world.wrong[right:right + wrong]:
            save_answer(attempt, option.question_id, option.pk)
        submit(attempt)
        return attempt

    def set_exam(self, **fields):
        Exam.objects.filter(pk=self.world.exam.pk).update(**fields)
        self.world.exam.refresh_from_db()

    def test_NFR_010_pass_mark_comes_from_the_exam(self):
        self.set_exam(pass_mark_percent=Decimal("40"))
        self.assertTrue(self.sit(4, 0).passed)  # 8 / 20 = 40%, inclusive
        self.set_exam(pass_mark_percent=Decimal("41"))
        self.assertFalse(self.sit(4, 0, self.world.stu_b).passed)  # same paper, same marks, stricter exam

    def test_NFR_010_negative_marking_switch_comes_from_the_exam(self):
        self.set_exam(negative_marking=True)
        self.assertEqual(self.sit(4, 4).score, Decimal("6"))  # 8 - 4 x 0.5
        self.set_exam(negative_marking=False)
        self.assertEqual(self.sit(4, 4, self.world.stu_b).score, Decimal("8"))

    def test_NFR_010_deduction_size_comes_from_each_question(self):
        Question.objects.filter(pk__in=[q.pk for q in self.world.questions]).update(negative_marks=Decimal("1"))
        self.assertEqual(self.sit(4, 4).score, Decimal("4"))  # 8 - 4 x 1

    def test_NFR_010_window_comes_from_the_exam(self):
        self.client.force_login(self.world.stu_a)
        start = reverse("attempt-start")
        now = self.world.exam.window_start + timedelta(hours=1)
        self.set_exam(window_start=now + timedelta(hours=1), window_end=now + timedelta(hours=2))
        self.assertEqual(self.client.post(start, {"exam": self.world.exam.pk}).status_code, 403)
        self.set_exam(window_start=now - timedelta(hours=2), window_end=now + timedelta(hours=2))
        self.assertEqual(self.client.post(start, {"exam": self.world.exam.pk}).status_code, 302)

    def test_NFR_010_faculty_can_set_every_policy_value_on_the_forms(self):
        self.assertTrue({"pass_mark_percent", "negative_marking", "duration_minutes"} <= set(ExamForm.base_fields))
        self.assertTrue({"window_start", "window_end"} <= set(ExamScheduleForm.base_fields))
        self.assertIn("negative_marks", QuestionForm.base_fields)

    def test_NFR_010_no_policy_value_is_hard_coded_in_the_scoring_code(self):
        found = []
        for name in SCORING_CODE:
            tree = ast.parse((Path(settings.BASE_DIR) / name).read_text(encoding="utf-8"))
            statuses = {id(k.value) for k in ast.walk(tree) if isinstance(k, ast.keyword) and k.arg == "status"}
            for node in ast.walk(tree):
                value = None
                if isinstance(node, ast.Constant) and type(node.value) in (int, float) and id(node) not in statuses:
                    value = str(node.value)  # HTTP status codes passed as status=... are not policy
                elif (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Decimal"
                      and node.args and isinstance(node.args[0], ast.Constant)):
                    value = node.args[0].value
                if value is not None and value not in ALLOWED:
                    found.append(f"{name}:{node.lineno}: {value}")
        self.assertEqual(found, [])
