"""Exam Repository (SAD 3.1): the Data layer. Every Business app reads and writes through these models."""
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class Role(models.TextChoices):
    STUDENT = "STUDENT", "Student"
    FACULTY = "FACULTY", "Faculty"
    ADMIN = "ADMIN", "Administrator"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **fields):
        user = self.model(email=self.normalize_email(email), **fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **fields):
        fields.update(role=Role.ADMIN, is_staff=True, is_superuser=True)
        return self.create_user(email, password, **fields)


class User(AbstractUser):
    """Signs in with email. FR-003: exactly one role -- a single required field the database checks."""

    username = None
    first_name = None
    last_name = None
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150)
    roll_number = models.CharField(max_length=20, unique=True, null=True, blank=True)  # Students only
    role = models.CharField(max_length=7, choices=Role.choices)
    consent_given_at = models.DateTimeField(null=True, blank=True)  # NFR-008: DPDP consent at registration

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]
    objects = UserManager()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(role__in=Role.values), name="user_has_one_valid_role"),
        ]

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name


class Course(models.Model):
    code = models.CharField(max_length=20)  # unique per semester, not globally (UT_014)
    title = models.CharField(max_length=200)
    semester = models.PositiveSmallIntegerField()
    archived = models.BooleanField(default=False)
    faculty = models.ManyToManyField(User, related_name="taught_courses", limit_choices_to={"role": Role.FACULTY})
    # A many-to-many row per (course, student) means enrolling twice still leaves one enrollment (FR-005).
    students = models.ManyToManyField(
        User, related_name="enrolled_courses", blank=True, limit_choices_to={"role": Role.STUDENT}
    )

    class Meta:
        constraints = [models.UniqueConstraint(fields=["code", "semester"], name="course_code_unique_per_semester")]

    def __str__(self):
        return f"{self.code} {self.title}"


class Question(models.Model):
    class Difficulty(models.TextChoices):
        EASY = "EASY", "Easy"
        MEDIUM = "MEDIUM", "Medium"
        HARD = "HARD", "Hard"

    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="questions")
    stem = models.TextField()
    topic = models.CharField(max_length=100)
    difficulty = models.CharField(max_length=6, choices=Difficulty.choices)
    positive_marks = models.DecimalField(max_digits=5, decimal_places=2)
    negative_marks = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="questions")
    # FR-009: editing a question in use makes a new row; the old one is kept, unchanged, and retired from the bank.
    version = models.PositiveIntegerField(default=1)
    previous = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="next_version"
    )
    retired = models.BooleanField(default=False)

    def __str__(self):
        return self.stem[:60]


class Option(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    text = models.TextField()
    is_correct = models.BooleanField(default=False)  # FR-029: never part of anything sent to a Student

    def __str__(self):
        return self.text[:60]


class Exam(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"

    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="exams")
    title = models.CharField(max_length=200)
    duration_minutes = models.PositiveIntegerField()
    total_marks = models.DecimalField(max_digits=6, decimal_places=2)
    instructions = models.TextField(blank=True)
    negative_marking = models.BooleanField(default=True)  # the deduction itself is Question.negative_marks
    shuffle_questions = models.BooleanField(default=False)
    shuffle_options = models.BooleanField(default=False)
    pass_mark_percent = models.DecimalField(max_digits=5, decimal_places=2)
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    window_start = models.DateTimeField(null=True, blank=True)
    window_end = models.DateTimeField(null=True, blank=True)
    results_published = models.BooleanField(default=False)  # FR-025/026
    questions = models.ManyToManyField(Question, through="ExamQuestion", related_name="exams")

    def __str__(self):
        return self.title


class ExamQuestion(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.PROTECT)
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ["order"]
        constraints = [models.UniqueConstraint(fields=["exam", "question"], name="question_once_per_exam")]


class Attempt(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.PROTECT, related_name="attempts")
    student = models.ForeignKey(User, on_delete=models.PROTECT, related_name="attempts")
    started_at = models.DateTimeField(auto_now_add=True)  # FR-016: the server's clock, never the client's
    submitted_at = models.DateTimeField(null=True, blank=True)
    score = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    percentage = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)  # FR-024
    passed = models.BooleanField(null=True, blank=True)  # FR-024: null until evaluated

    class Meta:
        constraints = [models.UniqueConstraint(fields=["exam", "student"], name="one_attempt_per_student")]


class Answer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT)
    option = models.ForeignKey(Option, on_delete=models.PROTECT, null=True, blank=True)  # null = unanswered
    saved_at = models.DateTimeField(auto_now=True)
    # FR-018: a row with no option is a visited, unanswered question; no row at all is Not Visited.
    marked_for_review = models.BooleanField(default=False)
    marks = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)  # FR-027, set on evaluation

    class Meta:
        constraints = [models.UniqueConstraint(fields=["attempt", "question"], name="one_answer_per_question")]


class FocusEvent(models.Model):
    """FR-028: the exam window lost focus. The time is the server's; the browser sends none."""

    attempt = models.ForeignKey(Attempt, on_delete=models.PROTECT, related_name="focus_events")
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["occurred_at", "id"]


class SignInFailure(models.Model):
    """NFR-012: one row per failed sign-in, keyed by the email typed, whether or not that account exists."""

    email = models.CharField(max_length=254, db_index=True)
    at = models.DateTimeField(auto_now_add=True)


class AppendOnly(Exception):
    """FR-030: audit entries are never changed or removed."""


class AuditQuerySet(models.QuerySet):
    """Prevent bulk modifications and deletions of audit entries."""

    def update(self, **kwargs):
        raise AppendOnly("The audit log is append-only")

    def delete(self):
        raise AppendOnly("The audit log is append-only")


class AuditEntry(models.Model):
    """FR-030: who did what to which entity, when, and the values before and after.

    Append-only three times over: save()/delete() below, AuditQuerySet, and SQLite triggers (migration 0006).
    """

    actor = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)  # null = the system itself
    action = models.CharField(max_length=40)
    entity = models.CharField(max_length=40)
    entity_id = models.PositiveBigIntegerField()
    changes = models.JSONField(default=dict, blank=True)
    at = models.DateTimeField(auto_now_add=True)

    objects = AuditQuerySet.as_manager()

    class Meta:
        ordering = ["-at", "-id"]

    def save(self, *args, **kwargs):
        """Allow creation, but refuse modifications to existing entries."""
        if not self._state.adding:
            raise AppendOnly("The audit log is append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Audit entries cannot be deleted."""
        raise AppendOnly("The audit log is append-only")
