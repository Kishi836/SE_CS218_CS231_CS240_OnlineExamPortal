"""NFR-002 -- a submitted 100-question attempt is evaluated within 5 seconds.

The time bound is the SRS pass condition. The query-count bound is what keeps it true as papers grow:
evaluation must not issue one query per answer.
"""
import time
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from attempts.services import save_answer, submit
from portal.testkit import World


class EvaluationTimeTests(TestCase):
    def setUp(self):
        self.world = World(n_questions=100)
        self.attempt = self.world.attempt()
        for i in range(100):  # 60 right, 30 wrong, 10 unanswered
            if i < 90:
                option = self.world.right[i] if i < 60 else self.world.wrong[i]
                save_answer(self.attempt, option.question_id, option.pk)

    def test_NFR_002_100_question_attempt_is_evaluated_within_5_seconds(self):
        started = time.perf_counter()
        submit(self.attempt)
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 5.0)
        self.assertEqual(self.attempt.score, Decimal("105"))  # 60 x 2 - 30 x 0.5, so the timed run did the real work

    def test_NFR_002_evaluation_query_count_does_not_grow_with_the_paper(self):
        with CaptureQueriesContext(connection) as queries:
            submit(self.attempt)
        # submit's update, the answers read, one bulk update of per-question marks, the attempt save, the refresh.
        self.assertLess(len(queries), 15, [q["sql"][:80] for q in queries])
