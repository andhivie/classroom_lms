from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('custom-logout/', views.custom_logout, name='custom_logout'),  # <-- baris ini
    # path('logout/', auth_views.LogoutView.as_view(), name='logout'),  # Hapus atau komentari yang lama
    path('bulk-add-students/', views.bulk_add_students, name='bulk_add_students'),
    path('attendance/<int:class_id>/', views.mark_attendance, name='mark_attendance'),
    path('class/<int:class_id>/assessments/', views.class_assessments, name='class_assessments'),
    path('assessment/add/<int:class_id>/', views.add_assessment, name='add_assessment'),
    path('assessment/<int:assessment_id>/scores/', views.enter_scores, name='enter_scores'),
    path('assessment/edit/<int:assessment_id>/', views.edit_assessment, name='edit_assessment'),
    path('assessment/delete/<int:assessment_id>/', views.delete_assessment, name='delete_assessment'),
    path('delete-student/<int:student_id>/<int:class_id>/', views.delete_student, name='delete_student'),
    path('reset-student-points/<int:student_id>/<int:class_id>/', views.reset_student_points, name='reset_student_points'),
    path('reset-class-points/<int:class_id>/', views.reset_class_points, name='reset_class_points'),
    path('delete-class/<int:class_id>/', views.delete_class, name='delete_class'),
    path('add-class/', views.add_class, name='add_class'),
    path('charts/', views.charts, name='charts'),
    path('student-feedback/<int:student_id>/<int:class_id>/', views.student_feedback, name='student_feedback'),
    path('export-class/<int:class_id>/', views.export_class_to_excel, name='export_class_excel'),
    path('reset-class-data/<int:class_id>/', views.reset_class_data, name='reset_class_data'),
    path('add-behavior/<int:student_id>/<int:class_id>/', views.add_behavior, name='add_behavior'),
    path('report-pdf/<int:student_id>/<int:class_id>/', views.generate_report_pdf, name='generate_report_pdf'),
    path('class/<int:class_id>/reports-zip/', views.download_class_reports_zip, name='download_class_reports_zip'),
    path('attendance/<int:class_id>/clear/', views.clear_attendance, name='clear_attendance'),
    path('class/<int:class_id>/averages/', views.student_averages, name='student_averages'),
    path('attendance/<int:class_id>/history/', views.student_attendance_history, name='student_attendance_history'),
    path('parent/', views.parent_login, name='parent_login'),
    path('parent/dashboard/', views.parent_dashboard, name='parent_dashboard'),
    path('generate-parent-code/<int:student_id>/', views.generate_parent_code, name='generate_parent_code'),
    path('parent/logout/', views.parent_logout, name='parent_logout'),
    path('download-parent-codes/<int:class_id>/', views.download_parent_codes, name='download_parent_codes'),
    path('backup-database/', views.backup_database, name='backup_database'),
    path('restore-database/', views.restore_database, name='restore_database'),
    path('profile/upload-picture/', views.upload_profile_picture, name='upload_profile_picture'),
    path('profile/delete-picture/', views.delete_profile_picture, name='delete_profile_picture'),
    path('sidebar-info/', views.sidebar_info, name='sidebar_info'),
]