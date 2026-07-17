from django.contrib import admin
from .models import (
    Semester, Class, Student, Enrollment, UserProfile,
    AttendanceSession, AttendanceRecord,
    BehaviorCategory, BehaviorEntry,
    AssessmentType, Assessment, Score,
    StudentFeedback
)

# Daftarkan semua model
admin.site.register(Semester)
admin.site.register(Class)
admin.site.register(Student)
admin.site.register(Enrollment)
admin.site.register(UserProfile)
admin.site.register(AttendanceSession)
admin.site.register(AttendanceRecord)
admin.site.register(BehaviorCategory)
admin.site.register(BehaviorEntry)
admin.site.register(AssessmentType)
admin.site.register(Assessment)
admin.site.register(Score)                # ← ini yang membuat /admin/lms/score/ bisa diakses
admin.site.register(StudentFeedback)

# Opsional: percantik tampilan admin
admin.site.index_title = "Classroom LMS Admin"
admin.site.site_header = "Classroom LMS Administration"