
from django import forms

from repository.models import Course, Exam, ExamQuestion, Question


class ExamForm(forms.ModelForm):
    # Override the model field so negative values reach our custom validation.
    duration_minutes = forms.IntegerField(
        min_value=None,
        label="Duration minutes",
    )

    class Meta:
        model = Exam
        fields = [
            "title",
            "course",
            "duration_minutes",
            "total_marks",
            "instructions",
            "negative_marking",
            "shuffle_questions",
            "shuffle_options",
            "pass_mark_percent",
        ]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        if user is not None:
            # Include assigned archived courses for validation, but do not
            # display them in the dropdown.
            assigned_courses = Course.objects.filter(
                faculty=user
            ).order_by("semester", "code")

            self.fields["course"].queryset = assigned_courses

            self.fields["course"].widget.choices = [
                ("", "---------"),
                *[
                    (course.pk, str(course))
                    for course in assigned_courses
                    if not course.archived
                ],
            ]

    def clean_course(self):
        course = self.cleaned_data["course"]

        if course.archived:
            raise forms.ValidationError("This course is archived")

        return course

    def clean_duration_minutes(self):
        duration = self.cleaned_data["duration_minutes"]

        if duration <= 0:
            raise forms.ValidationError(
                "Duration must be a positive number of minutes"
            )

        return duration

    def clean_pass_mark_percent(self):
        pass_mark = self.cleaned_data["pass_mark_percent"]

        if not 0 <= pass_mark <= 100:
            raise forms.ValidationError(
                "Pass mark must be between 0 and 100"
            )

        return pass_mark


class ExamQuestionForm(forms.Form):
    questions = forms.ModelMultipleChoiceField(
        queryset=Question.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )

    def __init__(self, *args, exam, **kwargs):
        super().__init__(*args, **kwargs)
        self.exam = exam

        # FR-009: superseded versions stay attached where they are but are never offered again.
        self.fields["questions"].queryset = Question.objects.filter(
            course=exam.course, retired=False
        ).order_by("id")

    def clean_questions(self):
        selected_questions = self.cleaned_data["questions"]

        # ModelMultipleChoiceField normally returns results in queryset order.
        # Reorder them according to the order submitted by the browser.
        submitted_ids = self.data.getlist("questions")
        questions_by_id = {
            question.pk: question for question in selected_questions
        }

        ordered_questions = []
        seen_ids = set()

        for raw_id in submitted_ids:
            try:
                question_id = int(raw_id)
            except (TypeError, ValueError):
                continue

            if question_id in seen_ids:
                raise forms.ValidationError(
                    "A question was selected more than once"
                )

            seen_ids.add(question_id)

            question = questions_by_id.get(question_id)
            if question is not None:
                ordered_questions.append(question)

        if len(ordered_questions) != len(questions_by_id):
            raise forms.ValidationError(
                "Invalid question selection"
            )

        existing_ids = set(
            ExamQuestion.objects.filter(
                exam=self.exam
            ).values_list("question_id", flat=True)
        )

        if any(
            question.pk in existing_ids
            for question in ordered_questions
        ):
            raise forms.ValidationError(
                "A question is already attached to this exam"
            )

        return ordered_questions


class ExamScheduleForm(forms.ModelForm):
    window_start = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )
    window_end = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )

    class Meta:
        model = Exam
        fields = ["window_start", "window_end"]

    def clean(self):
        cleaned_data = super().clean()
        window_start = cleaned_data.get("window_start")
        window_end = cleaned_data.get("window_end")
        if window_start and window_end and window_end <= window_start:
            self.add_error("window_end", "The window end must be later than the window start")
        return cleaned_data
