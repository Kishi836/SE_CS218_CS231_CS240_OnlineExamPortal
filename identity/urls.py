from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.register, name="register"),
    path("", views.home, name="home"),
    path("student/", views.student_dashboard, name="student-dashboard"),
    path("faculty/", views.faculty_dashboard, name="faculty-dashboard"),
    path("admin/", views.admin_dashboard, name="admin-dashboard"),

    path("admin/courses/", views.course_list, name="course-list"),
    path("admin/courses/new/", views.course_create, name="course-create"),
    path("admin/courses/<int:course_id>/edit/",
         views.course_edit, name="course-edit"),
    path("admin/courses/<int:course_id>/archive/",
         views.course_archive, name="course-archive"),

    path("admin/students/<int:student_id>/erase/", views.student_erase, name="student-erase"),  # NFR-008

    path("faculty/courses/", views.faculty_courses, name="faculty-courses"),
    path("courses/<int:course_id>/roster/",
         views.course_roster, name="course-roster"),
    path("courses/<int:course_id>/enroll/",
         views.course_enroll, name="course-enroll"),
    path(
        "courses/<int:course_id>/unenroll/<int:student_id>/",
        views.course_unenroll,
        name="course-unenroll",
    ),
]
