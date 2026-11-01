"""Results routes (SAD 3.1): publication, the scorecard and the results API (FR-025, FR-026, FR-027)."""
from django.urls import path

from . import views

urlpatterns = [
    path("faculty/exams/<int:exam_id>/results/", views.results_publish, name="results-publish"),  # FR-026
    path("api/results/<int:attempt_id>", views.result_api, name="result-api"),  # FR-025, IT_032
    path("results/<int:attempt_id>/", views.scorecard_page, name="scorecard"),  # FR-027
]
