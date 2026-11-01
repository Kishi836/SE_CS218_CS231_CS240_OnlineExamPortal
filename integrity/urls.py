"""Integrity routes (SAD 3.1): focus-loss events and the audit viewer (FR-028, FR-030)."""
from django.urls import path

from . import views

urlpatterns = [
    path("api/attempts/<int:pk>/focus-lost", views.focus_lost, name="attempt-focus-lost"),  # FR-028
    path("faculty/exams/<int:exam_id>/integrity/", views.exam_integrity, name="exam-integrity"),  # FR-028
]
