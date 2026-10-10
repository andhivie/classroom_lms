from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # ---------- Auth ----------
    path('', views.dashboard, name='dashboard'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('custom-logout/', views.custom_logout, name='custom_logout'),

    # ---------- Students ----------
    path('bulk-add-students/', views.bulk_add_students, name='bulk_add_students'),
    path('delete-student/<int:student_id>/<int:class_id>/', views.delete_student, name='delete_student'),
    path('edit-student/<int:student_id>/', views.edit_student, name='edit_student'),
    path('student/<int:student_id>/note/', views.student_note, name='student_note'),
    path('student/<int:student_id>/snapshot/', views.student_snapshot, name='student_snapshot'),
    path('student/<int:student_id>/class/<int:class_id>/focus/toggle/', views.toggle_focus_student, name='toggle_focus_student'),
    path('student/<int:student_id>/class/<int:class_id>/focus/reason/', views.update_focus_reason, name='update_focus_reason'),

    # ---------- Attendance ----------
    path('attendance/<int:class_id>/', views.mark_attendance, name='mark_attendance'),
    path('attendance/<int:class_id>/clear/', views.clear_attendance, name='clear_attendance'),
    path('attendance/<int:class_id>/history/', views.student_attendance_history, name='student_attendance_history'),

    # ---------- Assessments ----------
    path('class/<int:class_id>/assessments/', views.class_assessments, name='class_assessments'),
    path('assessment/add/<int:class_id>/', views.add_assessment, name='add_assessment'),
    path('assessment/<int:assessment_id>/scores/', views.enter_scores, name='enter_scores'),
    path('assessment/edit/<int:assessment_id>/', views.edit_assessment, name='edit_assessment'),
    path('assessment/delete/<int:assessment_id>/', views.delete_assessment, name='delete_assessment'),
    path('class/<int:class_id>/averages/', views.student_averages, name='student_averages'),

    # ---------- Behavior ----------
    path('add-behavior/<int:student_id>/<int:class_id>/', views.add_behavior, name='add_behavior'),
    path('convert-bonus/<int:student_id>/<int:class_id>/', views.convert_bonus, name='convert_bonus'),
    path('reset-student-points/<int:student_id>/<int:class_id>/', views.reset_student_points, name='reset_student_points'),
    path('reset-class-points/<int:class_id>/', views.reset_class_points, name='reset_class_points'),

    # ---------- Class management ----------
    path('add-class/', views.add_class, name='add_class'),
    path('delete-class/<int:class_id>/', views.delete_class, name='delete_class'),
    path('reset-class-data/<int:class_id>/', views.reset_class_data, name='reset_class_data'),
    path('class/<int:class_id>/settings/', views.class_settings, name='class_settings'),

    # ---------- Feedback ----------
    path('student-feedback/<int:student_id>/<int:class_id>/', views.student_feedback, name='student_feedback'),

    # ---------- Charts ----------
    path('charts/', views.charts, name='charts'),

    # ---------- Reports & Exports ----------
    path('export-class/<int:class_id>/', views.export_class_to_excel, name='export_class_excel'),
    path('report-pdf/<int:student_id>/<int:class_id>/', views.generate_report_pdf, name='generate_report_pdf'),
    path('class/<int:class_id>/reports-zip/', views.download_class_reports_zip, name='download_class_reports_zip'),

    # ---------- Profile ----------
    path('profile/upload-picture/', views.upload_profile_picture, name='upload_profile_picture'),
    path('profile/delete-picture/', views.delete_profile_picture, name='delete_profile_picture'),

    # ---------- Sidebar & Backup ----------
    path('sidebar-info/', views.sidebar_info, name='sidebar_info'),
    path('backup-database/', views.backup_database, name='backup_database'),
    path('restore-database/', views.restore_database, name='restore_database'),
    path('activity-log/add/', views.log_activity, name='log_activity'),

    # ---------- Semester management ----------
    path('semester/close/', views.close_semester_view, name='close_semester'),
    path('semester/archive/', views.archive_list_view, name='archive_list'),
    path('semester/<int:semester_id>/detail/', views.semester_detail_view, name='semester_detail'),
    path('semester/<int:semester_id>/restore/', views.restore_semester_view, name='restore_semester'),
    path('archive/class/<int:class_id>/', views.archived_class_detail_view, name='archived_class_detail'),
    path('archive/class/<int:class_id>/restore/', views.restore_class_view, name='restore_class'),

    # ---------- Student search & history ----------
    path('students/search/', views.student_search_view, name='student_search'),
    path('students/<int:student_id>/history/', views.student_history_view, name='student_history'),
]