import json

from django.contrib import messages
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from identity.access import roles
from repository.models import Question, Role

from . import services
from .forms import OptionFormSet, QuestionForm


def _forms_for_request(data, faculty):
    question_form = QuestionForm(data or None, faculty=faculty)
    option_formset = OptionFormSet(data or None, instance=Question())
    return question_form, option_formset


def _own_question_or_404(request, pk):
    """A current (not superseded) question in one of this Faculty member's courses."""
    return get_object_or_404(Question, pk=pk, retired=False, course__faculty=request.user)


@roles(Role.FACULTY)
def question_list(request):
    questions = (
        Question.objects.filter(course__faculty=request.user, retired=False)
        .select_related("course")
        .order_by("course__code", "id")
        .distinct()
    )
    return render(request, "questionbank/question_list.html", {"questions": questions})


@roles(Role.FACULTY)
def question_create(request):
    question_form, option_formset = _forms_for_request(request.POST or None, request.user)
    if request.method == "POST" and question_form.is_valid() and option_formset.is_valid():
        services.create(question_form, option_formset, request.user)
        messages.success(request, "Question created")
        return redirect("question-list")
    return render(
        request,
        "questionbank/question_form.html",
        {"form": question_form, "option_formset": option_formset, "heading": "Create a multiple-choice question"},
    )


@roles(Role.FACULTY)
def question_edit(request, pk):
    """FR-009: edit in place, or create a new version when the question is already in use."""
    original = _own_question_or_404(request, pk)
    frozen = services.in_use(original)
    question_form = QuestionForm(request.POST or None, instance=Question.objects.get(pk=pk), faculty=request.user)
    question_form.fields["course"].disabled = True  # a version stays in its course
    # Prefill only on GET: on POST, a row equal to its initial value counts as "unchanged" and is skipped.
    option_formset = OptionFormSet(
        request.POST or None,
        instance=Question(),
        initial=None if request.method == "POST" else list(original.options.order_by("id").values("text", "is_correct")),
    )
    if request.method == "POST" and question_form.is_valid() and option_formset.is_valid():
        saved = services.edit(original, question_form, option_formset, request.user)
        if saved.pk == original.pk:
            messages.success(request, "Question updated")
        else:
            messages.success(request, f"This question is in use, so your edit was saved as version {saved.version}")
        return redirect("question-list")
    return render(
        request,
        "questionbank/question_form.html",
        {
            "form": question_form,
            "option_formset": option_formset,
            "heading": f"Edit question (version {original.version})",
            "frozen": frozen,
        },
    )


@roles(Role.FACULTY)
@require_POST
def question_delete(request, pk):
    question = _own_question_or_404(request, pk)
    try:
        services.delete(question, request.user)
    except services.QuestionInUse as refusal:
        messages.error(request, str(refusal))
    else:
        messages.success(request, "Question deleted")
    return redirect("question-list")


def _api_form_data(payload):
    options = payload.get("options", [])
    if not isinstance(options, list):
        options = []
    data = {
        "course": payload.get("course", ""),
        "stem": payload.get("stem", ""),
        "topic": payload.get("topic", ""),
        "difficulty": payload.get("difficulty", ""),
        "positive_marks": payload.get("positive_marks", ""),
        "negative_marks": payload.get("negative_marks", ""),
        "options-TOTAL_FORMS": str(len(options)),
        "options-INITIAL_FORMS": "0",
        "options-MIN_NUM_FORMS": "0",
        "options-MAX_NUM_FORMS": "6",
    }
    for index, option in enumerate(options):
        if not isinstance(option, dict):
            option = {}
        data[f"options-{index}-text"] = option.get("text", "")
        if option.get("is_correct") is True:
            data[f"options-{index}-is_correct"] = "on"
    return data


def _api_errors(question_form, option_formset):
    errors = question_form.errors.get_json_data(escape_html=False)
    option_errors = [error for error in option_formset.errors if error]
    if option_errors:
        errors["options"] = option_errors
    if option_formset.non_form_errors():
        errors["options"] = list(option_formset.non_form_errors())
    return errors


@roles(Role.FACULTY)
def question_api(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"errors": {"body": ["Invalid JSON"]}}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"errors": {"body": ["Invalid JSON"]}}, status=400)

    question_form, option_formset = _forms_for_request(_api_form_data(payload), request.user)
    if not question_form.is_valid() or not option_formset.is_valid():
        return JsonResponse({"errors": _api_errors(question_form, option_formset)}, status=400)
    question = services.create(question_form, option_formset, request.user)
    return JsonResponse({"id": question.id}, status=201)
