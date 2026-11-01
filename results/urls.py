"""Results routes (SAD 3.1): publication, the scorecard and the results API (FR-025, FR-026, FR-027)."""
from django.urls import path

from . import views

urlpatterns = [
    path("results/<int:attempt_id>/", views.scorecard_page, name="scorecard"),  # FR-027
]
