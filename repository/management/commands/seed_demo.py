"""Seed the final-demo data set into an empty database.

    python manage.py migrate
    python manage.py seed_demo

Every account's password is DEMO_PASSWORD. Papers exist in every state: a Draft returned by the
Administrator, one sent to the Administrator (CR-02), one live now, one upcoming, and one past with
results published.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from attempts.services import submit
from repository.models import Answer, Attempt, Course, Exam, ExamQuestion, Option, Question, Role, User

DEMO_PASSWORD = "1234567890"

BANK = [
    ("Which SDLC model suits a project with well-understood, stable requirements?", "Requirements",
     ["Waterfall", "Spiral", "Prototyping", "RAD"], 0),
    ("Which IEEE standard describes the Software Requirements Specification?", "Requirements",
     ["IEEE 829", "IEEE 830", "IEEE 1012", "IEEE 1471"], 1),
    ("'The system shall respond within 2 seconds' is which kind of requirement?", "Requirements",
     ["Functional", "Non-functional", "Domain", "User"], 1),
    ("Which cohesion is considered the best?", "Design",
     ["Logical", "Temporal", "Functional", "Coincidental"], 2),
    ("Which coupling is considered the worst?", "Design",
     ["Data", "Stamp", "Control", "Content"], 3),
    ("In Scrum, who owns the product backlog?", "Agile",
     ["Scrum Master", "Product Owner", "Development Team", "Stakeholders"], 1),
    ("Which testing checks individual units in isolation?", "Testing",
     ["Unit testing", "System testing", "Acceptance testing", "Regression testing"], 0),
    ("Cyclomatic complexity of a graph with E=9, N=7, P=1 is", "Testing",
     ["2", "3", "4", "5"], 2),
]


class Command(BaseCommand):
    help = "Seed the final-demo data set (empty database only)."

    @transaction.atomic
    def handle(self, *args, **options):
        if User.objects.exists():
            raise CommandError("The database already has users; run this on a fresh, migrated database.")
        now = timezone.now()

        def user(email, role, name, roll=None):
            return User.objects.create_user(email, DEMO_PASSWORD, role=role, full_name=name, roll_number=roll,
                                            consent_given_at=now if role == Role.STUDENT else None)

        user("adm.a@pes.edu", Role.ADMIN, "Admin A")
        fac = user("fac.a@pes.edu", Role.FACULTY, "Dr. Faculty A")
        students = [user(f"stu.{c}@pesu.pes.edu", Role.STUDENT, f"Student {c.upper()}", f"PES1UG24CS00{i}")
                    for i, c in enumerate("abc", start=1)]

        se = Course.objects.create(code="UE24CS341A", title="Software Engineering", semester=5)
        se.faculty.add(fac)
        se.students.add(*students)

        questions = []
        for stem, topic, texts, correct in BANK:
            q = Question.objects.create(course=se, stem=stem, topic=topic, difficulty="MEDIUM",
                                        positive_marks=Decimal("2"), negative_marks=Decimal("0.5"), created_by=fac)
            for i, text in enumerate(texts):
                Option.objects.create(question=q, text=text, is_correct=i == correct)
            questions.append(q)

        def exam(title, qs, status, start=None, end=None, **extra):
            e = Exam.objects.create(
                course=se, title=title, duration_minutes=30, total_marks=Decimal(2 * len(qs)),
                pass_mark_percent=Decimal("40"), status=status,
                published_at=now if status == Exam.Status.PUBLISHED else None,
                window_start=start, window_end=end, shuffle_options=True,
                instructions="Single correct answer. +2 for correct, -0.5 for wrong, 0 if skipped.", **extra,
            )
            for i, q in enumerate(qs):
                ExamQuestion.objects.create(exam=e, question=q, order=i)
            return e

        published = Exam.Status.PUBLISHED
        exam("ISA-1 Practice Quiz", questions, published, now - timedelta(minutes=5), now + timedelta(hours=3))
        exam("Unit 3 Quiz", questions[3:7], published, now + timedelta(days=1), now + timedelta(days=1, hours=1))
        past = exam("Unit 1 Warm-up", questions[:5], published,
                    now - timedelta(days=2), now - timedelta(days=2) + timedelta(hours=2))
        exam("Unit 4 Quiz", questions[4:8], Exam.Status.SUBMITTED)  # CR-02: waiting in the Administrator's queue
        exam("Unit 2 Quiz", questions[1:4], Exam.Status.DRAFT,
             review_note="Add one more Design question before sending it again.")  # CR-02: returned

        # Two Students sat the past exam while its window was open; its results are published.
        for student, picks in ((students[1], [0, 1, 1, 2, 0]), (students[2], [0, 2, 1, 0, None])):
            attempt = Attempt.objects.create(exam=past, student=student)
            Attempt.objects.filter(pk=attempt.pk).update(started_at=past.window_start + timedelta(minutes=5))
            attempt.refresh_from_db()
            for q, pick in zip(questions[:5], picks):  # written directly: this attempt's clock ran out days ago
                if pick is not None:
                    Answer.objects.create(attempt=attempt, question=q, option=q.options.order_by("pk")[pick])
            submit(attempt, at=attempt.started_at + timedelta(minutes=20))
        Exam.objects.filter(pk=past.pk).update(results_published=True)

        self.stdout.write(f"Demo ready: {User.objects.count()} users, {Exam.objects.count()} exams, "
                          f"{Attempt.objects.count()} attempts. Every password is {DEMO_PASSWORD}.")
