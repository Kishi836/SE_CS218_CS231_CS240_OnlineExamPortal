"""ST_011 -- end-to-end automatic scoring of a full cohort (FR-022, FR-023, FR-024)."""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from portal.testkit import World, make_user
from repository.models import Attempt, Role


class CohortScoringTests(TestCase):
    def test_ST_011_five_students_are_scored_with_no_faculty_action(self):
        world = World(n_questions=25)  # +2 / -0.5, total 50, pass mark 40%
        students = [world.stu_a, world.stu_b] + [
            make_user(Role.STUDENT, f"stu.{c}@pesu.pes.edu", roll_number=f"PES1UG24CS0{i}") for i, c in enumerate("cde", 10)
        ]
        world.course.students.add(*students[2:])
        patterns = [(25, 0), (17, 4), (10, 0), (8, 8), (0, 25)]  # (right, wrong); the rest unanswered
        for student, (right, wrong) in zip(students, patterns):
            attempt = world.attempt(student)
            self.client.force_login(student)
            for option in world.right[:right] + world.wrong[right:right + wrong]:
                self.client.post(reverse("attempt-answer", args=[attempt.pk]), {"question": option.question_id, "option": option.pk})
            self.client.post(reverse("attempt-submit", args=[attempt.pk]))  # 1. sit and submit; 2. no Faculty action

        results = {a.student_id: (a.score, a.percentage, a.passed) for a in Attempt.objects.filter(exam=world.exam)}
        self.assertEqual(len(results), 5)
        self.assertTrue(all(score is not None for score, _, _ in results.values()))  # 3. all five evaluated
        # 4. two hand-computed from the answer key: 17 x 2 - 4 x 0.5 = 32 -> 64%, Pass; 8 x 2 - 8 x 0.5 = 12 -> 24%, Fail
        self.assertEqual(results[students[1].pk], (Decimal("32"), Decimal("64"), True))
        self.assertEqual(results[students[3].pk], (Decimal("12"), Decimal("24"), False))
        self.assertEqual(results[students[2].pk][2], True)  # 20 / 50 = 40%: the pass mark is inclusive
        self.assertEqual(results[students[4].pk], (Decimal("-12.5"), Decimal("-25"), False))  # all wrong goes negative
