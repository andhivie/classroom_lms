"""
Centralized behavior & scoring utilities for Classroom LMS.

All behavior point calculations, bonus conversions, and final score
computations MUST go through these functions. Never duplicate the logic
in views or templates.

Concept overview
----------------
Behavior points:
    - Positive entries: +1, +2, +3
    - Negative entries: -1, -2, -3

Per student per class per semester:
    total_positive   : sum of all positive points ever given
    total_negative   : sum of all negative points (stored as positive number)
    converted_points : total points already spent on conversions
    available_points : total_positive - total_negative - converted_points (clamped to 0)
    bonus_earned     : total academic bonus obtained from conversions

Final score:
    final_score = pure_academic_average + bonus_earned (capped at 100)
    Displayed as a whole number (no decimal).
"""

import math
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_semester(class_obj):
    """Return the semester of the class, or None."""
    return getattr(class_obj, 'semester', None)


def _behavior_entries_queryset(student, class_obj):
    """Return behavior entries for the given student/class/semester."""
    from lms.models import BehaviorEntry

    semester = _get_semester(class_obj)
    qs = BehaviorEntry.objects.filter(student=student)
    if semester is not None:
        qs = qs.filter(semester=semester)
    return qs


def _conversions_queryset(student, class_obj):
    """Return behavior conversions for the given student/class/semester."""
    from lms.models import BehaviorConversion

    semester = _get_semester(class_obj)
    qs = BehaviorConversion.objects.filter(student=student, class_obj=class_obj)
    if semester is not None:
        qs = qs.filter(semester=semester)
    return qs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_behavior_status(student, class_obj):
    """
    Compute the full behavior status for one student in one class.

    Available Points = total_positive - total_negative - converted_points
    (clamped to 0, never negative).

    Returns a dict with:
        total_positive, total_negative, net_points,
        converted_points, available_points, bonus_earned, conversions_count,
        daily_test_ready, daily_test_status, daily_test_threshold,
        points_needed_for_test, can_convert, conversion_error
    """
    entries = _behavior_entries_queryset(student, class_obj)

    total_positive = (
        entries
        .filter(points__gt=0)
        .aggregate(total=Coalesce(Sum('points'), Value(0)))['total']
        or 0
    )

    total_negative_raw = (
        entries
        .filter(points__lt=0)
        .aggregate(total=Coalesce(Sum('points'), Value(0)))['total']
        or 0
    )
    total_negative = abs(total_negative_raw)

    conversions = _conversions_queryset(student, class_obj)
    converted_points = (
        conversions
        .aggregate(total=Coalesce(Sum('points_used'), Value(0)))['total']
        or 0
    )
    bonus_earned = (
        conversions
        .aggregate(total=Coalesce(Sum('bonus_gained'), Value(0)))['total']
        or 0
    )
    conversions_count = conversions.count()

    # --- Available points: negatives now reduce available ---
    available_raw = total_positive - total_negative - converted_points
    available_points = max(available_raw, 0)

    # --- Daily Test requirement ---
    threshold = int(getattr(class_obj, 'min_points_for_daily_test', 0) or 0)

    if threshold <= 0:
        daily_test_status = 'disabled'
        daily_test_ready = True
        points_needed_for_test = 0
    elif available_points >= threshold:
        daily_test_status = 'ready'
        daily_test_ready = True
        points_needed_for_test = 0
    else:
        daily_test_status = 'not_ready'
        daily_test_ready = False
        points_needed_for_test = threshold - available_points

    # --- Can the teacher convert? ---
    points_per_conversion = int(getattr(class_obj, 'points_per_conversion', 0) or 0)
    bonus_per_conversion = int(getattr(class_obj, 'bonus_per_conversion', 0) or 0)
    max_bonus = int(getattr(class_obj, 'max_bonus', 0) or 0)

    conversion_error = None
    can_convert = True

    if points_per_conversion <= 0 or bonus_per_conversion <= 0:
        can_convert = False
        conversion_error = 'Conversion is disabled for this class.'
    elif max_bonus <= 0:
        can_convert = False
        conversion_error = 'Maximum bonus is set to 0.'
    elif available_points < points_per_conversion:
        can_convert = False
        needed = points_per_conversion - available_points
        conversion_error = f'Need {needed} more available point(s).'
    elif bonus_earned + bonus_per_conversion > max_bonus:
        remaining = max_bonus - bonus_earned
        can_convert = False
        conversion_error = f'Max bonus reached (can still gain +{max(remaining, 0)}).'

    return {
        'total_positive': int(total_positive),
        'total_negative': int(total_negative),
        'net_points': int(total_positive - total_negative),
        'converted_points': int(converted_points),
        'available_points': int(available_points),
        'bonus_earned': int(bonus_earned),
        'conversions_count': int(conversions_count),
        'daily_test_ready': daily_test_ready,
        'daily_test_status': daily_test_status,
        'daily_test_threshold': threshold,
        'points_needed_for_test': int(points_needed_for_test),
        'can_convert': can_convert,
        'conversion_error': conversion_error,
    }


def convert_behavior_bonus(student, class_obj, user=None):
    """
    Convert available behavior points into academic bonus for one student.
    Creates a BehaviorConversion record if the conversion is allowed.
    """
    from lms.models import BehaviorConversion

    status = calculate_behavior_status(student, class_obj)

    if not status['can_convert']:
        return {
            'success': False,
            'message': status['conversion_error'] or 'Conversion not allowed.',
            'conversion': None,
            'status': status,
        }

    points_per_conversion = class_obj.points_per_conversion
    bonus_per_conversion = class_obj.bonus_per_conversion

    conversion = BehaviorConversion.objects.create(
        student=student,
        class_obj=class_obj,
        semester=_get_semester(class_obj),
        points_used=points_per_conversion,
        bonus_gained=bonus_per_conversion,
        converted_by=user,
    )

    new_status = calculate_behavior_status(student, class_obj)

    return {
        'success': True,
        'message': (
            f"Converted {points_per_conversion} point(s) "
            f"into +{bonus_per_conversion} bonus for {student.name}."
        ),
        'conversion': conversion,
        'status': new_status,
    }


def calculate_final_score(student, class_obj):
    """
    Compute the final score for one student in one class.

    Final Score = Pure Academic Average + bonus_earned, capped at 100.
    Displayed as a whole number (no decimal places).
    """
    from lms.models import Assessment, Score

    assessments = list(Assessment.objects.filter(class_obj=class_obj))
    total_max = sum((a.max_points or 0.0) for a in assessments)

    total_earned = 0.0
    if assessments:
        scores = Score.objects.filter(student=student, assessment__in=assessments)
        total_earned = sum((s.points_earned or 0.0) for s in scores)

    if total_max > 0:
        academic_avg = (total_earned / total_max) * 100
    else:
        academic_avg = 0.0

    status = calculate_behavior_status(student, class_obj)
    bonus = status['bonus_earned']

    # Round to whole number, standard half-up rounding
    final_capped = min(academic_avg + bonus, 100.0)
    final_int = min(int(math.floor(final_capped + 0.5)), 100)

    return {
        'academic_average': round(academic_avg, 1),
        'bonus': int(bonus),
        'final_score': int(final_int),
        'total_earned': float(total_earned),
        'total_max': float(total_max),
        'has_assessments': total_max > 0,
    }


# ---------------------------------------------------------------------------
# Reset utilities
# ---------------------------------------------------------------------------

def reset_student_behavior(student, class_obj, full_reset=False):
    """
    Reset behavior points for one student in one class (scoped to the class's semester).

    If full_reset is True:
        - Deletes BehaviorEntry (positive & negative points)
        - Deletes BehaviorConversion (earned bonus + conversion history)

    If full_reset is False:
        - Deletes BehaviorEntry only
        - Keeps BehaviorConversion (student keeps earned bonus)

    Returns a dict with counts of deleted rows.
    """
    from lms.models import BehaviorEntry, BehaviorConversion

    semester = _get_semester(class_obj)

    entries_qs = BehaviorEntry.objects.filter(student=student)
    if semester is not None:
        entries_qs = entries_qs.filter(semester=semester)
    entries_deleted = entries_qs.count()
    entries_qs.delete()

    conversions_deleted = 0
    if full_reset:
        conversions_qs = BehaviorConversion.objects.filter(
            student=student, class_obj=class_obj
        )
        if semester is not None:
            conversions_qs = conversions_qs.filter(semester=semester)
        conversions_deleted = conversions_qs.count()
        conversions_qs.delete()

    return {
        'entries_deleted': entries_deleted,
        'conversions_deleted': conversions_deleted,
        'full_reset': full_reset,
    }


def reset_class_behavior(class_obj, full_reset=False):
    """
    Reset behavior points for ALL students in a class.

    Same semantics as reset_student_behavior, but for every enrolled student.
    """
    from lms.models import BehaviorEntry, BehaviorConversion, Enrollment

    semester = _get_semester(class_obj)
    student_ids = list(
        Enrollment.objects
        .filter(class_obj=class_obj, is_active=True)
        .values_list('student_id', flat=True)
    )

    entries_qs = BehaviorEntry.objects.filter(student_id__in=student_ids)
    if semester is not None:
        entries_qs = entries_qs.filter(semester=semester)
    entries_deleted = entries_qs.count()
    entries_qs.delete()

    conversions_deleted = 0
    if full_reset:
        conversions_qs = BehaviorConversion.objects.filter(
            student_id__in=student_ids, class_obj=class_obj
        )
        if semester is not None:
            conversions_qs = conversions_qs.filter(semester=semester)
        conversions_deleted = conversions_qs.count()
        conversions_qs.delete()

    return {
        'entries_deleted': entries_deleted,
        'conversions_deleted': conversions_deleted,
        'full_reset': full_reset,
        'student_count': len(student_ids),
    }