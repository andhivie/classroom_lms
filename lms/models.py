from django.db import models
from django.contrib.auth.models import User


class Semester(models.Model):
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Class(models.Model):
    name = models.CharField(max_length=100)
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name='classes')
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE, related_name='classes')
    schedule = models.CharField(max_length=255, blank=True)
    positive_behavior_cap = models.IntegerField(default=5, help_text="Max positive points for 100%")
    negative_behavior_cap = models.IntegerField(default=5, help_text="Max negative points for 0% contribution")
    is_archived = models.BooleanField(default=False, db_index=True, help_text="Set True when semester is closed")

    # ----- Priority 2: Behavior Point System configuration -----
    min_points_for_daily_test = models.IntegerField(
        default=5,
        help_text="Minimum available points required to take a Daily Test. Set 0 to disable."
    )
    points_per_conversion = models.IntegerField(
        default=25,
        help_text="Available points needed for one bonus conversion."
    )
    bonus_per_conversion = models.IntegerField(
        default=2,
        help_text="Academic bonus gained per conversion."
    )
    max_bonus = models.IntegerField(
        default=10,
        help_text="Maximum total bonus per student per semester."
    )

    def __str__(self):
        return f"{self.name} - {self.semester}"


class Student(models.Model):
    name = models.CharField(max_length=200, db_index=True)
    email = models.EmailField(blank=True)
    enrollment_date = models.DateField()
    is_active = models.BooleanField(default=True)
    parent_code = models.CharField(max_length=20, unique=True, null=True, blank=True, help_text="Kode akses orang tua")

    def __str__(self):
        return self.name


class Enrollment(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='enrollments')
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='enrollments')
    enrollment_date = models.DateField()
    drop_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        unique_together = ('student', 'class_obj')

    def __str__(self):
        return f"{self.student} in {self.class_obj}"


class UserProfile(models.Model):
    ROLE_CHOICES = (
        ('teacher', 'Teacher'),
        ('parent', 'Parent'),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    profile_picture = models.ImageField(upload_to='profile_pics/', null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"


class AttendanceSession(models.Model):
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='attendance_sessions')
    date = models.DateField(db_index=True)
    start_time = models.TimeField(blank=True, null=True)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ('class_obj', 'date')

    def __str__(self):
        return f"{self.class_obj.name} - {self.date}"


class AttendanceRecord(models.Model):
    STATUS_CHOICES = (
        ('present', 'Present'),
        ('late', 'Late'),
        ('absent', 'Absent'),
        ('excused', 'Excused'),
        ('sick', 'Sick'),
    )
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendance_records')
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name='records')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)
    marked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        unique_together = ('student', 'session')

    def __str__(self):
        return f"{self.student.name} - {self.session.date}: {self.status}"


# ========== BEHAVIOR MODELS ==========
class BehaviorCategory(models.Model):
    name = models.CharField(max_length=100)
    default_points = models.IntegerField()
    is_positive = models.BooleanField(default=True)
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, null=True, blank=True, related_name='behavior_categories')

    def __str__(self):
        return f"{self.name} ({self.default_points})"


class BehaviorEntry(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='behavior_entries')
    category = models.ForeignKey(BehaviorCategory, on_delete=models.SET_NULL, null=True)
    points = models.IntegerField()
    note = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    semester = models.ForeignKey(
        Semester,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='behavior_entries',
        help_text="Semester this entry belongs to. Used for auto-reset at new semester."
    )

    def __str__(self):
        return f"{self.student.name}: {self.points} points at {self.timestamp}"


# ========== ASSESSMENT MODELS ==========
class AssessmentType(models.Model):
    name = models.CharField(max_length=100)
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, null=True, blank=True, related_name='assessment_types')

    def __str__(self):
        return self.name


class Assessment(models.Model):
    name = models.CharField(max_length=200)  # Topic
    learning_objective = models.TextField(blank=True, null=True)
    assessment_type = models.ForeignKey(AssessmentType, on_delete=models.SET_NULL, null=True, blank=True)
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='assessments')
    date = models.DateField(db_index=True)
    max_points = models.FloatField()
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} - {self.class_obj.name}"


class Score(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='scores')
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name='scores')
    points_earned = models.FloatField()
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ('student', 'assessment')

    def __str__(self):
        return f"{self.student.name} - {self.assessment.name}: {self.points_earned}/{self.assessment.max_points}"


class StudentFeedback(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='feedbacks')
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='feedbacks')
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE, null=True, blank=True)
    feedback_text = models.TextField()
    generated_by_ai = models.BooleanField(default=False)
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'class_obj', 'semester')

    def __str__(self):
        return f"Feedback for {self.student.name} - {self.class_obj.name}"


class ActivityLog(models.Model):
    teacher = models.ForeignKey(User, on_delete=models.CASCADE)
    action = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)

class SemesterClosing(models.Model):
    """
    Record of a semester being closed. Stores audit trail and stats snapshot.
    """
    semester = models.OneToOneField(
        Semester,
        on_delete=models.CASCADE,
        related_name='closing_record'
    )
    closed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    closed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        help_text="Teacher who closed the semester"
    )
    total_classes = models.IntegerField(default=0)
    total_students = models.IntegerField(default=0)
    total_behavior_entries = models.IntegerField(default=0)
    notes = models.TextField(blank=True, help_text="Notes for reference")

    class Meta:
        ordering = ['-closed_at']

    def __str__(self):
        return f"Closing of {self.semester.name} on {self.closed_at.strftime('%d %b %Y')}"

class StudentPrivateNote(models.Model):
    """
    Teacher-only private notes about a student.
    Each teacher has their own note per student.
    Used to enrich AI-generated feedback with personal context.
    """
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='private_notes'
    )
    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='private_notes'
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('student', 'teacher')
        ordering = ['-updated_at']

    def __str__(self):
        return f"Note by {self.teacher.username} on {self.student.name}"

class BehaviorConversion(models.Model):
    """
    Log of behavior point conversions into academic bonus.
    Each row represents one 'Convert Bonus' action by a teacher.
    """
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='behavior_conversions'
    )
    class_obj = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name='behavior_conversions'
    )
    semester = models.ForeignKey(
        Semester,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='behavior_conversions'
    )
    points_used = models.IntegerField(
        help_text="Available points deducted at conversion time."
    )
    bonus_gained = models.IntegerField(
        help_text="Academic bonus added to the student's final score."
    )
    converted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        help_text="Teacher who performed the conversion."
    )
    converted_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-converted_at']

    def __str__(self):
        return (
            f"{self.student.name} - {self.class_obj.name}: "
            f"-{self.points_used} pts → +{self.bonus_gained} bonus"
        )