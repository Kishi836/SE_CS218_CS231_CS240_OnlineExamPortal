from django.urls import path

from . import views

urlpatterns = [
    # FR-030: Admin audit log
    path("admin/audit/", views.audit_log, name="audit-log"),


    # FR-028: Focus-loss recording
    path(
        "api/attempts/<int:pk>/focus-lost",
        views.focus_lost,
        name="attempt-focus-lost",
    ),

    # FR-028: Faculty integrity page
    path(
        "faculty/exams/<int:exam_id>/integrity/",
        views.exam_integrity,
        name="exam-integrity",
    ),
]
