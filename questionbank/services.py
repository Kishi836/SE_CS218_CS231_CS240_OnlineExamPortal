"""Question Bank Manager (SAD 3.1): saving, versioning (FR-009) and deleting questions."""
from django.db import transaction

from repository import audit
from repository.models import Answer, Exam, ExamQuestion, Option

AUDITED_FIELDS = ("stem", "topic", "difficulty", "positive_marks", "negative_marks")


class QuestionInUse(Exception):
    """FR-009: the question is frozen; the message is shown to Faculty as is."""


def in_use(question):
    """Frozen once it is in a published exam or any Student has answered it."""
    return (
        # CR-02: a paper waiting for the Administrator is frozen too, so it can't change under review.
        question.exams.exclude(status=Exam.Status.DRAFT).exists()
        or Answer.objects.filter(question=question).exists()
    )


def _options(option_formset):
    """The non-blank options the Faculty entered, in order."""
    return [
        {"text": f.cleaned_data["text"].strip(), "is_correct": bool(f.cleaned_data.get("is_correct"))}
        for f in option_formset.forms
        if f.cleaned_data.get("text", "").strip()
    ]


@transaction.atomic
def create(question_form, option_formset, faculty):
    question = question_form.save(commit=False)
    question.created_by = faculty
    question.save()
    options = _options(option_formset)
    Option.objects.bulk_create(Option(question=question, **o) for o in options)
    audit.record(faculty, "create", question)
    return question


def _snapshot(question, options):
    """FR-030: the audited values of a question, including its answer key (which option is correct)."""
    return {**{f: getattr(question, f) for f in AUDITED_FIELDS}, "options": options}


@transaction.atomic
def edit(original, question_form, option_formset, faculty):
    """Save Faculty's edit. A question in use is never changed: the edit becomes version N+1 instead (IT_013).

    `question_form` is bound to a copy of `original`, so `original` still holds the stored values.
    Returns the question that now carries the edit.
    """
    options = _options(option_formset)
    before = _snapshot(original, list(original.options.order_by("id").values("text", "is_correct")))
    question = question_form.save(commit=False)
    versioned = in_use(original)

    if versioned:
        question.pk = None
        question._state.adding = True
        question.version = original.version + 1
        question.previous = original
        question.created_by = faculty
        question.save()
        type(original).objects.filter(pk=original.pk).update(retired=True)
        # Drafts take the new version; published exams and past attempts keep the original.
        ExamQuestion.objects.filter(question=original, exam__status=Exam.Status.DRAFT).update(question=question)
    else:
        question.save()
        question.options.all().delete()  # nothing answered it, so no Answer points at these options

    Option.objects.bulk_create(Option(question=question, **o) for o in options)
    after = _snapshot(question, options)
    changes = {k: [before[k], after[k]] for k in after if before[k] != after[k]}
    if versioned:
        changes["previous_version"] = original.pk
    audit.record(faculty, "version" if versioned else "update", question, changes)
    return question


@transaction.atomic
def delete(question, faculty):
    """FR-009 / IT_014: refuse to delete a question in use; otherwise remove it from drafts and delete it."""
    if Answer.objects.filter(question=question).exists():
        raise QuestionInUse("This question has been attempted and cannot be deleted")
    if question.exams.exclude(status=Exam.Status.DRAFT).exists():
        raise QuestionInUse("This question is in an examination sent for scheduling or published, and cannot be deleted")
    ExamQuestion.objects.filter(question=question).delete()
    question.options.all().delete()
    if question.previous_id:  # deleting the newest version brings the one before it back into the bank
        type(question).objects.filter(pk=question.previous_id).update(retired=False)
    audit.record(faculty, "delete", question, {"stem": [question.stem, None]})
    question.delete()
