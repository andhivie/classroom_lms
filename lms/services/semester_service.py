"""
Semester closing & archiving service for Classroom LMS.

Responsibilities:
    - Close an active semester (with audit trail & auto-backup)
    - Archive all its classes
    - Preserve behavior points as historical data
    - Restore archive if needed (basic restore in this session)

Behavior points are NOT deleted — they remain tied to the old semester,
so historical reports keep working.
"""
from django.utils import timezone

from lms.services.backup_service import create_backup


def close_semester(semester, user, notes=''):
    """
    Close an active semester.

    Steps:
        1. Create a pre-close backup (safe-guard).
        2. Count stats (classes, students, behavior entries).
        3. Create SemesterClosing audit record.
        4. Mark semester inactive.
        5. Archive all classes in this semester.
        6. Log activity.

    Args:
        semester: Semester instance (must be is_active=True).
        user: Teacher (User) performing the close.
        notes: Optional notes string.

    Returns:
        dict with keys:
            success (bool)
            closing (SemesterClosing or None)
            backup_filename (str or None)
            total_classes, total_students, total_behavior_entries (int)
            error (str or None)
    """
    from lms.models import (
        Class, Enrollment, BehaviorEntry, SemesterClosing, ActivityLog
    )

    if not semester.is_active:
        return {
            'success': False,
            'closing': None,
            'backup_filename': None,
            'total_classes': 0,
            'total_students': 0,
            'total_behavior_entries': 0,
            'error': f"Semester '{semester.name}' is already inactive.",
        }

    # 1. Safety backup
    backup_result = create_backup(reason='pre_close_semester', rotate=False)
    backup_filename = backup_result.get('filename') if backup_result.get('success') else None

    # 2. Count stats
    classes = Class.objects.filter(semester=semester)
    total_classes = classes.count()
    total_students = Enrollment.objects.filter(
        class_obj__in=classes, is_active=True
    ).count()
    total_behavior_entries = BehaviorEntry.objects.filter(semester=semester).count()

    # 3. Create or update audit record (idempotent — safe to close twice)
    SemesterClosing.objects.filter(semester=semester).delete()
    closing = SemesterClosing.objects.create(
        semester=semester,
        closed_by=user,
        total_classes=total_classes,
        total_students=total_students,
        total_behavior_entries=total_behavior_entries,
        notes=notes.strip(),
    )

    # 4. Mark semester inactive
    semester.is_active = False
    semester.save(update_fields=['is_active'])

    # 5. Archive all classes (do NOT delete)
    classes.update(is_archived=True)

    # 6. Log activity
    try:
        ActivityLog.objects.create(
            teacher=user,
            action=f"Semester closed: {semester.name} "
                   f"({total_classes} classes, {total_students} students)"
        )
    except Exception:
        pass

    return {
        'success': True,
        'closing': closing,
        'backup_filename': backup_filename,
        'total_classes': total_classes,
        'total_students': total_students,
        'total_behavior_entries': total_behavior_entries,
        'error': None,
    }


def restore_class(class_obj, user):
    """
    Un-archive a single class AND its semester (Option B).

    Rationale: A class that is active should live in an active semester.
    So if we restore a class, we also:
        - Mark its semester as active
        - Delete the SemesterClosing record (closing notes are lost)
    """
    from lms.models import ActivityLog, SemesterClosing

    if not class_obj.is_archived:
        return {'success': False, 'error': 'Class is not archived.'}

    create_backup(reason='pre_restore_class', rotate=False)

    # Un-archive the class
    class_obj.is_archived = False
    class_obj.save(update_fields=['is_archived'])

    # Also restore its semester
    semester = class_obj.semester
    semester_restored = False
    if not semester.is_active:
        semester.is_active = True
        semester.save(update_fields=['is_active'])
        semester_restored = True

    # Delete closing record if exists
    SemesterClosing.objects.filter(semester=semester).delete()

    # Log
    log_msg = f"Class restored: {class_obj.name}"
    if semester_restored:
        log_msg += f" (semester '{semester.name}' reactivated)"
    try:
        ActivityLog.objects.create(teacher=user, action=log_msg)
    except Exception:
        pass

    return {
        'success': True,
        'semester_restored': semester_restored,
        'semester_name': semester.name,
        'error': None,
    }

def restore_semester(semester, user):
    """
    Restore an archived semester:
        - Set is_active = True
        - Un-archive all its classes
        - Delete the SemesterClosing record (closing notes will be lost)
    Creates a safety backup first.
    """
    from lms.models import Class, SemesterClosing, ActivityLog

    if semester.is_active:
        return {
            'success': False,
            'error': f"Semester '{semester.name}' is already active.",
        }

    # Safety backup
    create_backup(reason='pre_restore_semester', rotate=False)

    # Un-archive all classes in this semester
    classes_qs = Class.objects.filter(semester=semester)
    class_count = classes_qs.count()
    classes_qs.update(is_archived=False)

    # Delete the closing record (notes are lost — this is intentional)
    SemesterClosing.objects.filter(semester=semester).delete()

    # Mark semester active
    semester.is_active = True
    semester.save(update_fields=['is_active'])

    # Log
    try:
        ActivityLog.objects.create(
            teacher=user,
            action=f"Semester restored: {semester.name} ({class_count} classes un-archived)"
        )
    except Exception:
        pass

    return {
        'success': True,
        'class_count': class_count,
        'error': None,
    }

def get_semester_summary(semester):
    """
    Return a summary dict for a semester (works for active or archived).
    """
    from lms.models import Class, Enrollment, BehaviorEntry, SemesterClosing

    classes = Class.objects.filter(semester=semester)
    total_classes = classes.count()
    archived_count = classes.filter(is_archived=True).count()

    enrollments = Enrollment.objects.filter(class_obj__in=classes, is_active=True)
    total_students = enrollments.count()

    unique_students = enrollments.values('student').distinct().count()

    behavior_count = BehaviorEntry.objects.filter(semester=semester).count()

    closing = None
    try:
        closing = semester.closing_record
    except SemesterClosing.DoesNotExist:
        closing = None

    return {
        'semester': semester,
        'total_classes': total_classes,
        'archived_classes': archived_count,
        'total_students': total_students,
        'unique_students': unique_students,
        'total_behavior_entries': behavior_count,
        'closing': closing,
        'is_active': semester.is_active,
    }