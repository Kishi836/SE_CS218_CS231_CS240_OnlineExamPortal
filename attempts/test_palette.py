"""FR-018 -- one question at a time with the four-state palette (Test Plan UT_043, UT_044, IT_021)."""
from django.test import Client, TestCase
from django.urls import reverse

from portal.testkit import World
from repository.models import Answer

from . import services
from .services import ANSWERED, MARKED, NOT_ANSWERED, NOT_VISITED, palette


class PaletteTests(TestCase):
    def setUp(self):
        self.world = World(n_questions=25)
        self.attempt = self.world.attempt()
        self.ids = [q.id for q in self.world.questions]
        self.client.force_login(self.world.stu_a)

    def open(self, n):
        return self.client.get(reverse("attempt-question", args=[self.attempt.pk, n]))

    def test_paper_url_redirects_to_question_1(self):
        response = self.client.get(reverse("attempt-paper", args=[self.attempt.pk]))
        self.assertRedirects(response, reverse("attempt-question", args=[self.attempt.pk, 1]))

    def test_UT_043_palette_moves_through_every_state(self):
        q5 = self.ids[4]
        self.assertEqual(palette(self.attempt, self.ids)[4], NOT_VISITED)
        self.open(5)
        self.assertEqual(palette(self.attempt, self.ids)[4], NOT_ANSWERED)
        services.save_answer(self.attempt, q5, self.world.questions[4].options.first().id)
        self.assertEqual(palette(self.attempt, self.ids)[4], ANSWERED)
        Answer.objects.filter(attempt=self.attempt, question_id=q5).update(marked_for_review=True)
        self.assertEqual(palette(self.attempt, self.ids)[4], MARKED)

    def test_UT_044_exactly_one_stem_is_rendered(self):
        response = self.open(5)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f"<legend>Question 5 of 25. {self.world.questions[4].stem}</legend>",
            count=1,
            html=True,
        )
        for question in self.world.questions[:4] + self.world.questions[5:]:
            self.assertNotContains(response, f". {question.stem}</legend>")

    def test_IT_021_states_survive_reload_because_they_come_from_the_server(self):
        self.open(1)
        self.open(2)
        services.save_answer(self.attempt, self.ids[1], self.world.questions[1].options.first().id)
        Answer.objects.filter(attempt=self.attempt, question_id=self.ids[1]).update(marked_for_review=True)
        expected = palette(self.attempt, self.ids)
        reloaded = Client()
        reloaded.force_login(self.world.stu_a)
        response = reloaded.get(reverse("attempt-question", args=[self.attempt.pk, 1]))
        self.assertEqual([state for _, state in response.context["cells"]], expected)

    def test_question_out_of_range_is_404_and_other_students_attempt_is_404(self):
        self.assertEqual(self.open(26).status_code, 404)
        self.client.force_login(self.world.stu_b)
        self.assertEqual(self.open(1).status_code, 404)

    def test_revisiting_does_not_clear_a_saved_answer(self):
        question = self.world.questions[1]
        option = question.options.first()
        services.save_answer(self.attempt, question.id, option.id)
        response = self.open(2)
        self.assertEqual(response.context["saved"], option.id)

    def test_palette_states_have_accessible_text_labels(self):
        # Questions 1 to 4 in different states
        q2 = self.ids[1]
        services.save_answer(self.attempt, q2, self.world.questions[1].options.first().id)
        q3 = self.ids[2]
        Answer.objects.create(attempt=self.attempt, question_id=q3, marked_for_review=True)
        response = self.open(1)
        self.assertContains(response, '<span class="visually-hidden">Question 1, Not answered</span>')
        self.assertContains(response, '<span class="visually-hidden">Question 2, Answered</span>')
        self.assertContains(response, '<span class="visually-hidden">Question 3, Marked for review</span>')
        self.assertContains(response, '<span class="visually-hidden">Question 4, Not visited</span>')

