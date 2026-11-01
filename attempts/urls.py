
"""Attempt Session Manager and student exam visibility routes."""

from django.urls import path

from . import views

urlpatterns = [
    # PR3: FR-006 — enrolled students browse published exams.
    path(
        "student/exams/",
        views.student_exam_list,
        name="student-exam-list",
    ),
    path(
        "student/exams/<int:exam_id>/",
        views.student_exam_detail,
        name="student-exam-detail",
    ),

    # PR #70: attempt session management.
    path("api/attempts", views.start_attempt, name="attempt-start"),
    path("attempts/<int:pk>/", views.attempt_paper, name="attempt-paper"),
    path("attempts/<int:pk>/q/<int:n>/", views.attempt_question, name="attempt-question"),  # FR-018
    path("attempts/<int:pk>/submit", views.submit_attempt, name="attempt-submit"),
    path("api/attempts/<int:pk>/answers",
         views.save_answer, name="attempt-answer"),
    path("api/attempts/<int:pk>/remaining", views.attempt_remaining, name="attempt-remaining"),
]
