from django.urls import path

from . import views

urlpatterns = [
    path("faculty/exams/", views.exam_list, name="exam-list"),
    path("faculty/exams/new/", views.exam_create, name="exam-create"),
    path(
        "faculty/exams/<int:exam_id>/",
        views.exam_detail,
        name="exam-detail",
    ),
    path(
        "faculty/exams/<int:exam_id>/edit/",
        views.exam_edit,
        name="exam-edit",
    ),
    path(
        "faculty/exams/<int:exam_id>/questions/",
        views.exam_add_questions,
        name="exam-add-questions",
    ),
    path("faculty/exams/<int:exam_id>/submit/", views.exam_submit, name="exam-submit"),
    # CR-02: the Administrator schedules (and so publishes) the papers Faculty send.
    path("admin/exams/", views.admin_exam_queue, name="admin-exam-queue"),
    path("admin/exams/<int:exam_id>/schedule/", views.admin_exam_schedule, name="admin-exam-schedule"),
    path("admin/exams/<int:exam_id>/return/", views.admin_exam_return, name="admin-exam-return"),
]
