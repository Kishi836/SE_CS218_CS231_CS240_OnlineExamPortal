"""FR-019 -- every response is persisted as it is made; it can be changed, cleared or marked for review
(Test Plan UT_045, UT_046, UT_047, IT_023).

IT_022 (the response reaches the server within 5 s, measured in the browser's network panel) is manual:
the page posts on the `change` event itself, with no timer or batching in between.
"""
from django.test import Client, TestCase
from django.urls import reverse

from portal.testkit import PASSWORD, World
from repository.models import Answer


class AutosaveTests(TestCase):
    def setUp(self):
        self.world = World(n_questions=6)
        self.attempt = self.world.attempt()
        self.client.force_login(self.world.stu_a)
        self.url = reverse("attempt-answer", args=[self.attempt.pk])

    def post(self, n, option, **extra):
        """Answer question n (1-based) with "right", "wrong" or "" (clear)."""
        q = self.world.questions[n - 1]
        value = {"right": self.world.right[n - 1].pk, "wrong": self.world.wrong[n - 1].pk, "": ""}[option]
        return self.client.post(self.url, {"question": q.pk, "option": value, **extra})

    def stored(self, n):
        return Answer.objects.get(attempt=self.attempt, question=self.world.questions[n - 1])

    def test_UT_045_response_is_persisted_with_no_save_button(self):
        self.assertEqual(self.post(1, "right").status_code, 200)
        self.assertEqual(self.stored(1).option, self.world.right[0])
        self.assertNotContains(self.client.get(reverse("attempt-paper", args=[self.attempt.pk]), follow=True), ">Save<")

    def test_UT_046_changing_a_response_keeps_one_row_with_the_new_value(self):
        self.post(3, "right")
        self.post(3, "wrong")
        self.assertEqual(Answer.objects.filter(attempt=self.attempt).count(), 1)
        self.assertEqual(self.stored(3).option, self.world.wrong[2])

    def test_UT_047_clearing_a_response_stores_it_empty(self):
        self.post(3, "right")
        self.post(3, "")
        self.assertIsNone(self.stored(3).option)
        self.assertContains(self.client.get(reverse("attempt-paper", args=[self.attempt.pk]), follow=True), "Clear response")

    def test_review_flag_is_set_kept_and_cleared(self):
        self.post(2, "right", marked_for_review="1")
        self.post(2, "wrong")  # a caller that leaves the flag out keeps it
        self.assertTrue(self.stored(2).marked_for_review)
        self.post(2, "wrong", marked_for_review="0")
        self.assertFalse(self.stored(2).marked_for_review)

    def test_bad_input_is_rejected_and_nothing_is_stored(self):
        q = self.world.questions[0]
        for data in ({"option": self.world.right[0].pk}, {"question": q.pk, "option": "x"},
                     {"question": q.pk, "option": "", "marked_for_review": "yes"},
                     {"question": 999999, "option": ""},
                     {"question": q.pk, "option": self.world.right[1].pk}):  # another question's option
            self.assertEqual(self.client.post(self.url, data).status_code, 400, data)
        self.assertFalse(Answer.objects.exists())

    def test_IT_023_saved_responses_survive_a_browser_that_never_submits(self):
        for n in range(1, 4):
            self.post(n, "right")
        fresh = Client()  # the killed browser is gone; a new one signs in
        fresh.post(reverse("login"), {"email": self.world.stu_a.email, "password": PASSWORD})
        saved = [
            fresh.get(reverse("attempt-question", args=[self.attempt.pk, n])).context["saved"]
            for n in range(1, 7)
        ]
        self.assertEqual(saved, [o.pk for o in self.world.right[:3]] + [None] * 3)

    def test_submitted_attempt_refuses_changes_clears_and_flags(self):
        self.post(1, "right")
        self.client.post(reverse("attempt-submit", args=[self.attempt.pk]))
        self.assertEqual(self.post(1, "", marked_for_review="1").status_code, 409)
        self.assertEqual(self.stored(1).option, self.world.right[0])
        self.assertFalse(self.stored(1).marked_for_review)
