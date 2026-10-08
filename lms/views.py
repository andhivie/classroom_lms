from django.shortcuts import render, redirect
import time
import logging
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import date, datetime
from django.db import models
from django.contrib.auth import logout
import requests
from django.conf import settings
import pandas as pd
from django.db.models import Sum, Count, Q, Avg, F, FloatField, Case, When, Value
from django.db.models.functions import Coalesce
import json
from .models import Semester
from lms.services.dashboard_service import (
    get_behavior_summary,
    get_attendance_summary,
)

from lms.services.behavior_service import (
    calculate_behavior_status,
    calculate_final_score,
)

from lms.constants import STANDARD_ASSESSMENT_TYPES, DAILY_TEST_TYPE

from .models import (
    Class, UserProfile, Enrollment, Student, AttendanceSession, AttendanceRecord,
    BehaviorEntry, BehaviorCategory, AssessmentType, Assessment, Score,
    StudentFeedback, Semester, ActivityLog
)

# ---------- Helper Functions ----------
def custom_logout(request):
    logout(request)
    return redirect('login')


# ---------- Dashboard ----------
@login_required
def dashboard(request):
    start_time = time.perf_counter()

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return HttpResponse("You do not have a profile. Please contact the administrator.")

    if profile.role != 'teacher':
        return HttpResponse("Access restricted to teachers.")

    url_class_id = request.GET.get('class_id')
    selected_class_id = None
    if url_class_id and url_class_id.isdigit():
        selected_class_id = int(url_class_id)

    all_classes = Class.objects.filter(teacher=request.user, is_archived=False)
    if selected_class_id:
        classes = all_classes.filter(id=selected_class_id)
    else:
        classes = all_classes

    search_query = request.GET.get('search', '').strip()
    if search_query:
        matching_students = Student.objects.filter(
            enrollments__class_obj__in=classes,
            name__icontains=search_query
        ).distinct()
        classes = classes.filter(enrollments__student__in=matching_students).distinct()

    class_data = []
    all_students_data = []

    for cls in classes:
        enrollments = (
            Enrollment.objects
            .filter(class_obj=cls, is_active=True)
            .select_related('student')
            .order_by('student__name')
        )

        student_ids = [e.student_id for e in enrollments]
        if not student_ids:
            class_data.append({'class': cls, 'students': []})
            continue

        # Attendance summary (still uses legacy helper — behavior is now via service)
        attendance_dict = get_attendance_summary(student_ids, cls)

        students_data = []
        for enrollment in enrollments:
            student = enrollment.student

            if search_query and search_query.lower() not in student.name.lower():
                continue

            sid = student.id

            behavior_status = calculate_behavior_status(student, cls)
            score_data = calculate_final_score(student, cls)

            att_data = attendance_dict.get(
                sid,
                {'total_sessions': 0, 'present_count': 0, 'percentage': 0.0}
            )
            total_sessions = att_data['total_sessions']
            present_count = att_data['present_count']
            attendance_summary = (
                f"{present_count}/{total_sessions}" if total_sessions > 0 else "0/0"
            )
            attendance_percentage = att_data['percentage']

            students_data.append({
                'student': student,
                'attendance_summary': attendance_summary,
                'attendance_percentage': round(attendance_percentage, 1),
                # Behavior (from service)
                'total_positive': behavior_status['total_positive'],
                'total_negative': behavior_status['total_negative'],
                'net_points': behavior_status['net_points'],
                'available_points': behavior_status['available_points'],
                'converted_points': behavior_status['converted_points'],
                'bonus_earned': behavior_status['bonus_earned'],
                'daily_test_ready': behavior_status['daily_test_ready'],
                'daily_test_status': behavior_status['daily_test_status'],
                'points_needed_for_test': behavior_status['points_needed_for_test'],
                'can_convert': behavior_status['can_convert'],
                'conversion_error': behavior_status['conversion_error'],
                # Academic (pure)
                'academic_avg': score_data['academic_average'],
                'final_score': score_data['final_score'] if score_data['has_assessments'] else None,
            })

        class_data.append({'class': cls, 'students': students_data})
        all_students_data.extend(students_data)

    highest_positive = None
    highest_negative = None
    highest_final = None

    if all_students_data:
        highest_positive = max(all_students_data, key=lambda x: x['total_positive'])
        highest_negative = max(all_students_data, key=lambda x: x['total_negative'])
        students_with_final = [s for s in all_students_data if s['final_score'] is not None]
        if students_with_final:
            highest_final = max(students_with_final, key=lambda x: x['final_score'])

    context = {
        'class_data': class_data,
        'all_classes': all_classes,
        'selected_class_id': selected_class_id,
        'user': request.user,
        'semesters': Semester.objects.all(),
        'highest_positive': highest_positive,
        'highest_negative': highest_negative,
        'highest_final': highest_final,
        'search_query': search_query,
    }

    if request.GET.get('partial') == 'true':
        return render(request, 'lms/partials/_dashboard_content.html', context)

    elapsed = time.perf_counter() - start_time
    print(f"Dashboard loaded in {elapsed:.3f} seconds")

    return render(request, 'lms/teacher_dashboard.html', context)

# ---------- Bulk Add Students ----------
@login_required
def bulk_add_students(request):
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Profile missing.'}, status=403)
        messages.error(request, "You do not have a profile.")
        return redirect('dashboard')
    if profile.role != 'teacher':
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Only teachers can access.'}, status=403)
        messages.error(request, "Only teachers can access this page.")
        return redirect('dashboard')

    classes = Class.objects.filter(teacher=request.user)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.method == 'POST':
        class_id = request.POST.get('class_id')
        student_data = request.POST.get('student_data', '').strip()

        if not class_id:
            msg = "Please select a class."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.error(request, msg)
            return redirect('bulk_add_students')
        if not student_data:
            msg = "Please enter student data."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.error(request, msg)
            return redirect('bulk_add_students')

        try:
            target_class = Class.objects.get(id=class_id, teacher=request.user)
        except Class.DoesNotExist:
            msg = "Invalid class selected."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.error(request, msg)
            return redirect('bulk_add_students')

        lines = student_data.split('\n')
        added_count = 0
        skipped_count = 0
        errors = []

        for line_num, line in enumerate(lines, start=1):
            line = line.strip()
            if not line:
                continue

            parts = [p.strip() for p in line.split(',')]
            name = parts[0]
            email = parts[1] if len(parts) > 1 and parts[1] else ''

            if not name:
                errors.append(f"Line {line_num}: Name is empty.")
                continue

            if Student.objects.filter(name__iexact=name, enrollments__class_obj=target_class).exists():
                skipped_count += 1
                errors.append(f"Line {line_num}: Student '{name}' already enrolled. Skipped.")
                continue

            student = Student.objects.create(
                name=name, email=email,
                enrollment_date=date.today(), is_active=True
            )
            Enrollment.objects.create(
                student=student, class_obj=target_class,
                enrollment_date=date.today(), is_active=True
            )
            added_count += 1

        messages_list = []
        if added_count:
            messages_list.append(f"Successfully added {added_count} new student(s).")
        if skipped_count:
            messages_list.append(f"Skipped {skipped_count} student(s).")
        for err in errors[:5]:
            messages_list.append(err)

        final_message = " ".join(messages_list)
        if is_ajax:
            return JsonResponse({
                'status': 'ok',
                'message': final_message,
                'added': added_count,
                'skipped': skipped_count,
                'errors': errors[:5]
            })
        if added_count:
            messages.success(request, f"Successfully added {added_count} new student(s).")
        if skipped_count:
            messages.warning(request, f"Skipped {skipped_count} student(s).")
        for err in errors[:5]:
            messages.error(request, err)
        return redirect('dashboard')

    context = {'classes': classes}
    return render(request, 'lms/bulk_add_students.html', context)


# ---------- Mark Attendance ----------
@login_required
def mark_attendance(request, class_id):
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Profile missing.'}, status=403)
        messages.error(request, "Profile missing.")
        return redirect('dashboard')
    if profile.role != 'teacher':
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Only teachers can access.'}, status=403)
        messages.error(request, "Only teachers can access.")
        return redirect('dashboard')

    try:
        class_obj = Class.objects.get(id=class_id, teacher=request.user)
    except Class.DoesNotExist:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Class not found.'}, status=404)
        messages.error(request, "Class not found.")
        return redirect('dashboard')

    date_str = request.GET.get('date')
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            request.session['attendance_date'] = date_str
        except ValueError:
            selected_date = timezone.now().date()
    elif 'attendance_date' in request.session:
        selected_date = datetime.strptime(request.session['attendance_date'], '%Y-%m-%d').date()
    else:
        selected_date = timezone.now().date()

    if request.GET.get('reset_date'):
        request.session.pop('attendance_date', None)
        return redirect('mark_attendance', class_id=class_id)

    session, _ = AttendanceSession.objects.get_or_create(
        class_obj=class_obj,
        date=selected_date,
        defaults={'start_time': timezone.now().time() if selected_date == timezone.now().date() else None}
    )

    enrollments = Enrollment.objects.filter(
        class_obj=class_obj, is_active=True
    ).select_related('student').order_by('student__name')
    students = [e.student for e in enrollments]

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.method == 'POST':
        for student in students:
            status = request.POST.get(f'status_{student.id}')
            if status:
                AttendanceRecord.objects.update_or_create(
                    student=student,
                    session=session,
                    defaults={'status': status, 'marked_by': request.user}
                )
        formatted_date = selected_date.strftime("%A, %d %B %Y")
        message = f"Attendance for {class_obj.name} on {formatted_date} saved."
        if is_ajax:
            return JsonResponse({'status': 'ok', 'message': message})
        messages.success(request, message)
        return redirect('mark_attendance', class_id=class_id)

    existing_records = {
        record.student_id: record.status
        for record in AttendanceRecord.objects.filter(session=session)
    }
    students_with_status = [(student, existing_records.get(student.id, '')) for student in students]

    if is_ajax and request.GET.get('partial') == 'true':
        context = {
            'students_with_status': students_with_status,
            'status_choices': AttendanceRecord.STATUS_CHOICES,
        }
        return render(request, 'lms/partials/_attendance_table.html', context)

    context = {
        'class_obj': class_obj,
        'students_with_status': students_with_status,
        'status_choices': AttendanceRecord.STATUS_CHOICES,
        'selected_date': selected_date,
    }
    return render(request, 'lms/mark_attendance.html', context)


# ---------- Assessments ----------
@login_required
def add_assessment(request, class_id):
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Profile missing.'}, status=403)
        messages.error(request, "Profile missing.")
        return redirect('dashboard')
    if profile.role != 'teacher':
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Only teachers can access.'}, status=403)
        messages.error(request, "Only teachers can access.")
        return redirect('dashboard')

    try:
        class_obj = Class.objects.get(id=class_id, teacher=request.user)
    except Class.DoesNotExist:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Class not found.'}, status=404)
        messages.error(request, "Class not found.")
        return redirect('dashboard')

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.method == 'POST':
        name = request.POST.get('name')
        learning_objective = request.POST.get('learning_objective', '')
        assessment_type_name = request.POST.get('assessment_type')
        date_str = request.POST.get('date')
        max_points = request.POST.get('max_points')
        notes = request.POST.get('notes', '')

        if not all([name, date_str, max_points, assessment_type_name]):
            msg = "Please fill all required fields."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.error(request, msg)
            return redirect('add_assessment', class_id=class_id)

        if assessment_type_name not in STANDARD_ASSESSMENT_TYPES:
            msg = (
                f"Invalid assessment type '{assessment_type_name}'. "
                f"Must be one of: {', '.join(STANDARD_ASSESSMENT_TYPES)}."
            )
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.error(request, msg)
            return redirect('add_assessment', class_id=class_id)

        assessment_type, _ = AssessmentType.objects.get_or_create(
            name=assessment_type_name,
            class_obj=class_obj
        )
        assessment = Assessment.objects.create(
            name=name,
            learning_objective=learning_objective,
            assessment_type=assessment_type,
            class_obj=class_obj,
            date=date_str,
            max_points=float(max_points),
            notes=notes
        )
        msg = f"Assessment '{name}' added successfully."
        if is_ajax:
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d')
                formatted_date = dt.strftime('%b %d, %Y')
            except:
                formatted_date = date_str
            return JsonResponse({
                'status': 'ok',
                'message': msg,
                'assessment': {
                    'id': assessment.id,
                    'name': assessment.name,
                    'learning_objective': assessment.learning_objective or '—',
                    'type': assessment.assessment_type.name if assessment.assessment_type else '—',
                    'date': formatted_date,
                    'max_points': assessment.max_points,
                }
            })
        messages.success(request, msg)
        return redirect('class_assessments', class_id=class_id)

    assessment_types = AssessmentType.objects.filter(class_obj=class_obj)
    context = {'class_obj': class_obj, 'assessment_types': assessment_types}
    return render(request, 'lms/add_assessment.html', context)

@login_required
def enter_scores(request, assessment_id):
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Profile missing.'}, status=403)
        messages.error(request, "Profile missing.")
        return redirect('dashboard')
    if profile.role != 'teacher':
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Only teachers can access.'}, status=403)
        messages.error(request, "Only teachers can access.")
        return redirect('dashboard')

    try:
        assessment = Assessment.objects.get(id=assessment_id)
        class_obj = assessment.class_obj
        if class_obj.teacher != request.user:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'Not allowed.'}, status=403)
            messages.error(request, "Not allowed.")
            return redirect('dashboard')
    except Assessment.DoesNotExist:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Assessment not found.'}, status=404)
        messages.error(request, "Assessment not found.")
        return redirect('dashboard')

    enrollments = Enrollment.objects.filter(
        class_obj=class_obj, is_active=True
    ).select_related('student').order_by('student__name')
    students = [e.student for e in enrollments]

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.method == 'POST':
        saved_count = 0
        errors = []

        for student in students:
            points_str = request.POST.get(f'score_{student.id}')
            notes = request.POST.get(f'notes_{student.id}', '')

            if points_str and points_str.strip():
                try:
                    points = float(points_str.replace(',', '.'))
                    points = max(0, min(points, assessment.max_points))

                    Score.objects.update_or_create(
                        student=student,
                        assessment=assessment,
                        defaults={
                            'points_earned': points,
                            'notes': notes
                        }
                    )
                    saved_count += 1
                except (ValueError, TypeError):
                    errors.append(f"Invalid score for {student.name}: '{points_str}'")

        # Build user-facing message
        if saved_count > 0:
            msg = f"{saved_count} score(s) saved for '{assessment.name}'."
            if errors:
                msg += " However, some scores failed: " + "; ".join(errors[:3])
                if len(errors) > 3:
                    msg += f" (and {len(errors) - 3} more)"
        else:
            if errors:
                msg = f"❌ No scores were saved. Errors: {'; '.join(errors[:3])}"
            else:
                msg = "No scores entered. No changes made."

        if is_ajax:
            return JsonResponse({'status': 'ok' if saved_count > 0 else 'warning', 'message': msg})

        # Fallback non-AJAX
        if saved_count > 0:
            messages.success(request, msg)
        else:
            messages.warning(request, msg)

        return redirect('class_assessments', class_id=class_obj.id)

    existing_scores = {score.student_id: score for score in Score.objects.filter(assessment=assessment)}
    students_with_scores = []
    for student in students:
        score_obj = existing_scores.get(student.id)
        students_with_scores.append((
            student,
            score_obj.points_earned if score_obj else None,
            score_obj.notes if score_obj else ''
        ))

    context = {
        'assessment': assessment,
        'class_obj': class_obj,
        'students_with_scores': students_with_scores,
        'max_points': assessment.max_points,
    }
    return render(request, 'lms/enter_scores.html', context)


@login_required
def edit_assessment(request, assessment_id):
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Profile missing.'}, status=403)
        messages.error(request, "Profile missing.")
        return redirect('dashboard')
    if profile.role != 'teacher':
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Only teachers can access.'}, status=403)
        messages.error(request, "Only teachers can access.")
        return redirect('dashboard')

    try:
        assessment = Assessment.objects.get(id=assessment_id)
        class_obj = assessment.class_obj
        if class_obj.teacher != request.user:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'Not allowed.'}, status=403)
            messages.error(request, "Not allowed.")
            return redirect('dashboard')
    except Assessment.DoesNotExist:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Assessment not found.'}, status=404)
        messages.error(request, "Assessment not found.")
        return redirect('dashboard')

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.method == 'POST':
        name = request.POST.get('name')
        learning_objective = request.POST.get('learning_objective', '')
        assessment_type_name = request.POST.get('assessment_type')
        date_str = request.POST.get('date')
        max_points = request.POST.get('max_points')
        notes = request.POST.get('notes', '')

        if not all([name, date_str, max_points, assessment_type_name]):
            msg = "All required fields must be filled."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.error(request, msg)
            return redirect('edit_assessment', assessment_id=assessment_id)

        if assessment_type_name not in STANDARD_ASSESSMENT_TYPES:
            msg = (
                f"Invalid assessment type '{assessment_type_name}'. "
                f"Must be one of: {', '.join(STANDARD_ASSESSMENT_TYPES)}."
            )
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.error(request, msg)
            return redirect('edit_assessment', assessment_id=assessment_id)

        assessment_type, _ = AssessmentType.objects.get_or_create(
            name=assessment_type_name,
            class_obj=class_obj
        )
        assessment.name = name
        assessment.learning_objective = learning_objective
        assessment.assessment_type = assessment_type
        assessment.date = date_str
        assessment.max_points = float(max_points)
        assessment.notes = notes
        assessment.save()

        msg = f"Assessment '{name}' updated successfully."
        if is_ajax:
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d')
                formatted_date = dt.strftime('%b %d, %Y')
            except:
                formatted_date = date_str
            return JsonResponse({
                'status': 'ok',
                'message': msg,
                'assessment': {
                    'id': assessment.id,
                    'name': assessment.name,
                    'learning_objective': assessment.learning_objective or '—',
                    'type': assessment.assessment_type.name if assessment.assessment_type else '—',
                    'date': formatted_date,
                    'max_points': assessment.max_points,
                }
            })
        messages.success(request, msg)
        return redirect('class_assessments', class_id=class_obj.id)

    if is_ajax:
        data = {
            'id': assessment.id,
            'name': assessment.name,
            'learning_objective': assessment.learning_objective or '',
            'assessment_type': assessment.assessment_type.name if assessment.assessment_type else '',
            'date': assessment.date.strftime('%Y-%m-%d'),
            'max_points': assessment.max_points,
            'notes': assessment.notes or '',
        }
        return JsonResponse(data)

    assessment_types = AssessmentType.objects.filter(class_obj=class_obj)
    context = {'assessment': assessment, 'class_obj': class_obj, 'assessment_types': assessment_types}
    return render(request, 'lms/edit_assessment.html', context)


@login_required
def delete_assessment(request, assessment_id):
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Profile missing.'}, status=403)
        messages.error(request, "Profile missing.")
        return redirect('dashboard')
    if profile.role != 'teacher':
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Only teachers can access.'}, status=403)
        messages.error(request, "Only teachers can access.")
        return redirect('dashboard')

    try:
        assessment = Assessment.objects.get(id=assessment_id)
        class_obj = assessment.class_obj
        if class_obj.teacher != request.user:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'Not allowed.'}, status=403)
            messages.error(request, "Not allowed.")
            return redirect('dashboard')
    except Assessment.DoesNotExist:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Assessment not found.'}, status=404)
        messages.error(request, "Assessment not found.")
        return redirect('dashboard')

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.method == 'POST':
        assessment_name = assessment.name
        assessment.delete()
        msg = f"Assessment '{assessment_name}' deleted successfully."
        if is_ajax:
            return JsonResponse({'status': 'ok', 'message': msg})
        messages.success(request, msg)
        return redirect('class_assessments', class_id=class_obj.id)

    return redirect('class_assessments', class_id=class_obj.id)


@login_required
def class_assessments(request, class_id):
    try:
        class_obj = Class.objects.get(id=class_id, teacher=request.user)
    except Class.DoesNotExist:
        messages.error(request, "Class not found.")
        return redirect('dashboard')

    from django.db.models import Avg, F, Case, When, FloatField

    assessments = Assessment.objects.filter(class_obj=class_obj).annotate(
        avg_percentage=Avg(
            Case(
                When(max_points__gt=0, then=F('scores__points_earned') * 100.0 / F('max_points')),
                default=None,
                output_field=FloatField()
            )
         )
    ).order_by('-date')
    
    assessment_averages = []
    for ass in assessments:
        scores = Score.objects.filter(assessment=ass)
        if scores.exists():
            avg = scores.aggregate(avg=models.Avg('points_earned'))['avg']
            max_points = ass.max_points
            percentage = (avg / max_points) * 100 if max_points else 0
            assessment_averages.append({
                'name': ass.name,
                'avg': round(avg, 1),
                'max': max_points,
                'percentage': round(percentage, 1),
                'count': scores.count()
            })
        else:
            assessment_averages.append({
                'name': ass.name,
                'avg': None,
                'max': ass.max_points,
                'percentage': None,
                'count': 0
            })
    
    if request.GET.get('partial') == 'true':
        return render(request, 'lms/partials/_assessments_table.html', {'assessments': assessments})
    
    context = {
        'class_obj': class_obj,
        'assessments': assessments,
        'assessment_averages': assessment_averages,
    }
    return render(request, 'lms/class_assessments.html', context)


@login_required
def student_averages(request, class_id):
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        messages.error(request, "Profile missing.")
        return redirect('dashboard')
    if profile.role != 'teacher':
        messages.error(request, "Only teachers can access.")
        return redirect('dashboard')

    try:
        class_obj = Class.objects.get(id=class_id, teacher=request.user)
    except Class.DoesNotExist:
        messages.error(request, "Class not found.")
        return redirect('dashboard')

    enrollments = Enrollment.objects.filter(
        class_obj=class_obj, is_active=True
    ).select_related('student').order_by('student__name')
    
    students = [e.student for e in enrollments]
    
    all_assessments = Assessment.objects.filter(class_obj=class_obj)
    total_max = all_assessments.aggregate(total=Sum('max_points'))['total'] or 0

    student_data = []
    for student in students:
        scores = Score.objects.filter(student=student, assessment__in=all_assessments)
        total_earned = scores.aggregate(total=Sum('points_earned'))['total'] or 0
        if total_max > 0:
            avg_percentage = (total_earned / total_max) * 100
        else:
            avg_percentage = None

        student_data.append({
            'student': student,
            'avg_percentage': avg_percentage,
            'total_assessments': all_assessments.count(),
            'assessed_count': scores.count(),
        })
    
    context = {
        'class_obj': class_obj,
        'student_data': student_data,
    }
    return render(request, 'lms/student_averages.html', context)

# ---------- Behavior ----------
@login_required
def add_behavior(request, student_id, class_id):
    """
    Add a behavior point entry for a student in a class.

    Accepts POST parameter 'points' with one of: +1, +2, +3, -1, -2, -3.
    Uses the centralized behavior_service for all calculations.
    """
    from lms.services.behavior_service import (
        calculate_behavior_status,
        calculate_final_score,
    )

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    # --- Teacher check ---
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Profile missing.'}, status=403)
    if profile.role != 'teacher':
        return JsonResponse({'status': 'error', 'message': 'Only teachers can access.'}, status=403)

    # --- Get class & student ---
    try:
        class_obj = Class.objects.get(id=class_id, teacher=request.user)
        student = Student.objects.get(id=student_id, is_active=True)
    except (Class.DoesNotExist, Student.DoesNotExist):
        return JsonResponse({'status': 'error', 'message': 'Class or student not found.'}, status=404)

    # --- Validate points ---
    points_str = request.POST.get('points')
    if not points_str:
        return JsonResponse({'status': 'error', 'message': 'Points not specified.'}, status=400)

    try:
        points = int(points_str)
    except ValueError:
        return JsonResponse({'status': 'error', 'message': 'Invalid points value.'}, status=400)

    allowed_values = {1, 2, 3, -1, -2, -3}
    if points not in allowed_values:
        return JsonResponse({
            'status': 'error',
            'message': f'Invalid points value {points}. Allowed: +1, +2, +3, -1, -2, -3.'
        }, status=400)

    # --- Create the entry ---
    category, _ = BehaviorCategory.objects.get_or_create(
        name='Quick Point',
        defaults={'default_points': points, 'is_positive': points > 0}
    )

    BehaviorEntry.objects.create(
        student=student,
        category=category,
        points=points,
        note=f"Quick {'positive' if points > 0 else 'negative'} point from dashboard",
        recorded_by=request.user,
        semester=class_obj.semester,
    )

    # --- Recalculate via service ---
    status = calculate_behavior_status(student, class_obj)
    score = calculate_final_score(student, class_obj)

    return JsonResponse({
        'status': 'ok',
        'message': f'Added {points:+d} point(s) to {student.name}.',
        'new_final_score': score['final_score'],
        'total_positive': status['total_positive'],
        'total_negative': status['total_negative'],
        'net_points': status['net_points'],
        'available_points': status['available_points'],
        'bonus_earned': status['bonus_earned'],
        'conversions_count': status['conversions_count'],
        'can_convert': status['can_convert'],
        'conversion_error': status['conversion_error'],
        'daily_test_status': status['daily_test_status'],
        'daily_test_ready': status['daily_test_ready'],
        'points_needed_for_test': status['points_needed_for_test'],
    })

@login_required
def convert_bonus(request, student_id, class_id):
    """
    Convert a student's available behavior points into academic bonus.
    Only allowed when the class configuration permits it.
    """
    from lms.services.behavior_service import convert_behavior_bonus

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Profile missing.'}, status=403)
    if profile.role != 'teacher':
        return JsonResponse({'status': 'error', 'message': 'Only teachers can access.'}, status=403)

    try:
        class_obj = Class.objects.get(id=class_id, teacher=request.user)
        student = Student.objects.get(id=student_id, is_active=True)
    except (Class.DoesNotExist, Student.DoesNotExist):
        return JsonResponse({'status': 'error', 'message': 'Class or student not found.'}, status=404)

    result = convert_behavior_bonus(student, class_obj, user=request.user)

    if not result['success']:
        return JsonResponse({'status': 'error', 'message': result['message']})

    status = result['status']
    return JsonResponse({
        'status': 'ok',
        'message': result['message'],
        'available_points': status['available_points'],
        'bonus_earned': status['bonus_earned'],
        'converted_points': status['converted_points'],
    })

# ---------- Reset Points ----------
@login_required
def reset_student_points(request, student_id, class_id):
    from lms.services.behavior_service import (
        calculate_behavior_status,
        calculate_final_score,
        reset_student_behavior,
    )

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Profile missing.'}, status=403)
    if profile.role != 'teacher':
        return JsonResponse({'status': 'error', 'message': 'Only teachers can access.'}, status=403)

    try:
        class_obj = Class.objects.get(id=class_id, teacher=request.user)
        student = Student.objects.get(id=student_id)
    except (Class.DoesNotExist, Student.DoesNotExist):
        return JsonResponse({'status': 'error', 'message': 'Class or student not found.'}, status=404)

    full_reset = request.POST.get('full_reset', 'false').lower() == 'true'

    result = reset_student_behavior(student, class_obj, full_reset=full_reset)

    status = calculate_behavior_status(student, class_obj)
    score = calculate_final_score(student, class_obj)

    label = "Full reset" if full_reset else "Points reset"
    return JsonResponse({
        'status': 'ok',
        'message': f'{label} applied to {student.name}.',
        'total_positive': status['total_positive'],
        'total_negative': status['total_negative'],
        'available_points': status['available_points'],
        'bonus_earned': status['bonus_earned'],
        'new_final_score': score['final_score'],
    })

@login_required
def reset_class_points(request, class_id):
    from lms.services.behavior_service import reset_class_behavior

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Profile missing.'}, status=403)
    if profile.role != 'teacher':
        return JsonResponse({'status': 'error', 'message': 'Only teachers can access.'}, status=403)

    try:
        class_obj = Class.objects.get(id=class_id, teacher=request.user)
    except Class.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Class not found.'}, status=404)

    full_reset = request.POST.get('full_reset', 'false').lower() == 'true'

    result = reset_class_behavior(class_obj, full_reset=full_reset)

    label = "Full reset" if full_reset else "Points reset"
    return JsonResponse({
        'status': 'ok',
        'message': f'{label} applied to {class_obj.name}.',
    })

@login_required
def close_semester_view(request):
    """
    Close the active semester: mark inactive, archive classes, write audit.
    Accessible to teacher only.
    """
    from lms.services.semester_service import close_semester, get_semester_summary
    from lms.services.backup_service import get_backup_status

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        messages.error(request, "Profile missing.")
        return redirect('dashboard')
    if profile.role != 'teacher':
        messages.error(request, "Only teachers can access.")
        return redirect('dashboard')

    # Find the active semester(s) this teacher is involved in
    active_semesters = Semester.objects.filter(
        is_active=True,
        classes__teacher=request.user
    ).distinct()

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.method == 'POST':
        semester_id = request.POST.get('semester_id')
        notes = request.POST.get('notes', '').strip()

        if not semester_id:
            msg = "Please select a semester to close."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.error(request, msg)
            return redirect('close_semester')

        try:
            semester = Semester.objects.get(id=semester_id, is_active=True)
        except Semester.DoesNotExist:
            msg = "Active semester not found."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.error(request, msg)
            return redirect('close_semester')

        # Safety: verify teacher has classes in this semester
        if not Class.objects.filter(semester=semester, teacher=request.user).exists():
            msg = "You don't have classes in this semester."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.error(request, msg)
            return redirect('close_semester')

        result = close_semester(semester, user=request.user, notes=notes)

        if not result['success']:
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': result['error']})
            messages.error(request, result['error'])
            return redirect('close_semester')

        msg = (
            f"Semester '{semester.name}' closed successfully. "
            f"{result['total_classes']} classes archived, "
            f"{result['total_students']} students kept in history."
        )
        if is_ajax:
            return JsonResponse({
                'status': 'ok',
                'message': msg,
                'backup_created': result['backup_filename'],
                'total_classes': result['total_classes'],
                'total_students': result['total_students'],
            })
        messages.success(request, msg)
        return redirect('dashboard')

    # GET — build context
    summaries = [get_semester_summary(s) for s in active_semesters]
    backup_status = get_backup_status()

    context = {
        'active_semesters': summaries,
        'backup_status': backup_status,
        'user': request.user,
    }
    return render(request, 'lms/semester_close.html', context)

@login_required
def archive_list_view(request):
    """
    List all semesters the teacher has been involved in:
    - Active semester(s) with green badge
    - Archived semesters (sorted newest first)
    Each item shows quick stats.
    """
    from lms.services.semester_service import get_semester_summary

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        messages.error(request, "Profile missing.")
        return redirect('dashboard')
    if profile.role != 'teacher':
        messages.error(request, "Only teachers can access.")
        return redirect('dashboard')

    # Semesters this teacher has classes in
    semesters = (
        Semester.objects
        .filter(classes__teacher=request.user)
        .distinct()
        .order_by('-start_date')
    )

    active_summaries = []
    archived_summaries = []

    for sem in semesters:
        summary = get_semester_summary(sem)
        if sem.is_active:
            active_summaries.append(summary)
        else:
            archived_summaries.append(summary)

    context = {
        'active_summaries': active_summaries,
        'archived_summaries': archived_summaries,
        'total_archived': len(archived_summaries),
        'user': request.user,
    }
    return render(request, 'lms/semester_archive_list.html', context)


@login_required
def semester_detail_view(request, semester_id):
    """
    Read-only detail of one semester:
    - Info & stats
    - List of classes (archived or active)
    - Closing notes (if archived)
    - Actions: download all reports per class
    """
    from lms.services.semester_service import get_semester_summary

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        messages.error(request, "Profile missing.")
        return redirect('dashboard')
    if profile.role != 'teacher':
        messages.error(request, "Only teachers can access.")
        return redirect('dashboard')

    try:
        semester = Semester.objects.get(id=semester_id)
    except Semester.DoesNotExist:
        messages.error(request, "Semester not found.")
        return redirect('archive_list')

    # Access control: teacher must have at least one class in this semester
    if not Class.objects.filter(semester=semester, teacher=request.user).exists():
        messages.error(request, "You don't have classes in this semester.")
        return redirect('archive_list')

    summary = get_semester_summary(semester)

    # Classes in this semester for this teacher
    classes = (
        Class.objects
        .filter(semester=semester, teacher=request.user)
        .order_by('name')
    )

    # Enrich with quick stats
    class_list = []
    for cls in classes:
        enrollment_count = Enrollment.objects.filter(
            class_obj=cls, is_active=True
        ).count()
        assessment_count = Assessment.objects.filter(class_obj=cls).count()
        class_list.append({
            'class': cls,
            'enrollment_count': enrollment_count,
            'assessment_count': assessment_count,
        })

    context = {
        'semester': semester,
        'summary': summary,
        'class_list': class_list,
        'is_archived': not semester.is_active,
        'closing': summary.get('closing'),
        'user': request.user,
    }
    return render(request, 'lms/semester_detail.html', context)


@login_required
def archived_class_detail_view(request, class_id):
    """
    Read-only view of a class in the archive.
    Shows student list with behavior summary & final score.
    No add/edit/delete actions.
    """
    from lms.services.behavior_service import (
        calculate_behavior_status,
        calculate_final_score,
    )

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        messages.error(request, "Profile missing.")
        return redirect('dashboard')
    if profile.role != 'teacher':
        messages.error(request, "Only teachers can access.")
        return redirect('dashboard')

    try:
        class_obj = Class.objects.get(id=class_id, teacher=request.user)
    except Class.DoesNotExist:
        messages.error(request, "Class not found.")
        return redirect('archive_list')

    # Must be archived to enter read-only mode
    if not class_obj.is_archived:
        return redirect('dashboard')

    enrollments = (
        Enrollment.objects
        .filter(class_obj=class_obj, is_active=True)
        .select_related('student')
        .order_by('student__name')
    )

    students_data = []
    for enr in enrollments:
        student = enr.student
        behavior = calculate_behavior_status(student, class_obj)
        score = calculate_final_score(student, class_obj)

        # Attendance summary
        att_records = AttendanceRecord.objects.filter(
            student=student, session__class_obj=class_obj
        )
        total_sessions = att_records.count()
        present_count = att_records.filter(
            status__in=['present', 'late', 'excused', 'sick']
        ).count()
        attendance_summary = (
            f"{present_count}/{total_sessions}"
            if total_sessions > 0 else "0/0"
        )

        students_data.append({
            'student': student,
            'attendance_summary': attendance_summary,
            'total_positive': behavior['total_positive'],
            'total_negative': behavior['total_negative'],
            'available_points': behavior['available_points'],
            'bonus_earned': behavior['bonus_earned'],
            'final_score': score['final_score'] if score['has_assessments'] else None,
            'academic_average': score['academic_average'],
        })

    context = {
        'class_obj': class_obj,
        'semester': class_obj.semester,
        'students_data': students_data,
        'total_students': len(students_data),
        'user': request.user,
    }
    return render(request, 'lms/archived_class_detail.html', context)

@login_required
def student_search_view(request):
    """
    Search students across all semesters (active + archived).
    Teacher can only see students enrolled in their own classes.
    Inactive students are shown with a badge; can be hidden via checkbox.
    """
    from lms.services.behavior_service import calculate_final_score

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        messages.error(request, "Profile missing.")
        return redirect('dashboard')
    if profile.role != 'teacher':
        messages.error(request, "Only teachers can access.")
        return redirect('dashboard')

    query = request.GET.get('q', '').strip()
    hide_inactive = request.GET.get('hide_inactive') == 'on'

    results = []
    total_count = 0
    inactive_count = 0

    if query:
        # Base query: students enrolled in this teacher's classes
        students_qs = (
            Student.objects
            .filter(
                name__icontains=query,
                enrollments__class_obj__teacher=request.user,
            )
            .distinct()
            .order_by('name')
        )

        total_count = students_qs.count()
        inactive_count = students_qs.filter(is_active=False).count()

        # Apply inactive filter if requested
        if hide_inactive:
            students_qs = students_qs.filter(is_active=True)

        students = students_qs[:50]

        for student in students:
            enrollments = (
                Enrollment.objects
                .filter(student=student, class_obj__teacher=request.user)
                .select_related('class_obj', 'class_obj__semester')
                .order_by('-class_obj__semester__start_date', 'class_obj__name')
            )

            semesters_data = []
            for enr in enrollments:
                cls = enr.class_obj
                score_data = calculate_final_score(student, cls)
                semesters_data.append({
                    'semester': cls.semester,
                    'class_obj': cls,
                    'final_score': score_data['final_score'] if score_data['has_assessments'] else None,
                    'academic_avg': score_data['academic_average'],
                    'is_archived': cls.is_archived,
                })

            results.append({
                'student': student,
                'enrollments': semesters_data,
                'semester_count': len(semesters_data),
                'is_active': student.is_active,
            })

    context = {
        'query': query,
        'results': results,
        'result_count': len(results),
        'total_count': total_count,
        'inactive_count': inactive_count,
        'hide_inactive': hide_inactive,
        'user': request.user,
    }
    return render(request, 'lms/student_search.html', context)

@login_required
def student_history_view(request, student_id):
    """
    Full historical profile of one student across all semesters
    that the current teacher has taught them.
    """
    from lms.services.behavior_service import (
        calculate_behavior_status,
        calculate_final_score,
    )

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        messages.error(request, "Profile missing.")
        return redirect('dashboard')
    if profile.role != 'teacher':
        messages.error(request, "Only teachers can access.")
        return redirect('dashboard')

    try:
        student = Student.objects.get(id=student_id)
    except Student.DoesNotExist:
        messages.error(request, "Student not found.")
        return redirect('student_search')

    # Access control: teacher must have at least one enrollment with this student
    enrollments = (
        Enrollment.objects
        .filter(student=student, class_obj__teacher=request.user)
        .select_related('class_obj', 'class_obj__semester')
        .order_by('-class_obj__semester__start_date', 'class_obj__name')
    )

    if not enrollments.exists():
        messages.error(request, "You don't have access to this student's record.")
        return redirect('student_search')

    timeline = []
    total_present = 0
    total_sessions_all = 0
    final_scores = []
    total_bonus_all = 0

    for enr in enrollments:
        cls = enr.class_obj
        behavior = calculate_behavior_status(student, cls)
        score_data = calculate_final_score(student, cls)

        # Attendance
        att_records = AttendanceRecord.objects.filter(
            student=student, session__class_obj=cls
        )
        total_sessions = att_records.count()
        present_count = att_records.filter(
            status__in=['present', 'late', 'excused', 'sick']
        ).count()

        total_present += present_count
        total_sessions_all += total_sessions

        att_pct = round((present_count / total_sessions * 100), 1) if total_sessions > 0 else 0

        # Feedback for this class
        feedback = StudentFeedback.objects.filter(
            student=student, class_obj=cls
        ).order_by('-last_updated').first()

        final_score_val = score_data['final_score'] if score_data['has_assessments'] else None
        if final_score_val is not None:
            final_scores.append(final_score_val)

        total_bonus_all += behavior['bonus_earned']

        timeline.append({
            'semester': cls.semester,
            'class_obj': cls,
            'is_archived': cls.is_archived,
            'attendance_summary': f"{present_count}/{total_sessions}" if total_sessions > 0 else "0/0",
            'attendance_pct': att_pct,
            'total_positive': behavior['total_positive'],
            'total_negative': behavior['total_negative'],
            'bonus_earned': behavior['bonus_earned'],
            'academic_avg': score_data['academic_average'],
            'final_score': final_score_val,
            'feedback_text': feedback.feedback_text if feedback else '',
            'feedback_date': feedback.last_updated if feedback else None,
        })

    # Overall stats
    overall_att_pct = round((total_present / total_sessions_all * 100), 1) if total_sessions_all > 0 else 0
    avg_final = round(sum(final_scores) / len(final_scores), 1) if final_scores else None

    # Chart data (chronological order — oldest first)
    chronological = list(reversed(timeline))
    chart_labels = [f"{item['semester'].name}" for item in chronological]
    chart_data = [
        item['final_score'] if item['final_score'] is not None else 0
        for item in chronological
    ]

    context = {
        'student': student,
        'timeline': timeline,
        'total_semesters': len(timeline),
        'overall_attendance_pct': overall_att_pct,
        'average_final_score': avg_final,
        'total_bonus': total_bonus_all,
        'has_multiple_semesters': len(timeline) > 1,
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data),
        'user': request.user,
    }
    return render(request, 'lms/student_history.html', context)

@login_required
def restore_semester_view(request, semester_id):
    """Restore an archived semester back to active."""
    from lms.services.semester_service import restore_semester

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method.'}, status=405)

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Profile missing.'}, status=403)
    if profile.role != 'teacher':
        return JsonResponse({'status': 'error', 'message': 'Access restricted.'}, status=403)

    try:
        semester = Semester.objects.get(id=semester_id)
    except Semester.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Semester not found.'}, status=404)

    # Access control
    if not Class.objects.filter(semester=semester, teacher=request.user).exists():
        return JsonResponse({'status': 'error', 'message': 'Not allowed.'}, status=403)

    result = restore_semester(semester, user=request.user)

    if not result['success']:
        return JsonResponse({'status': 'error', 'message': result['error']})

    return JsonResponse({
        'status': 'ok',
        'message': f"Semester '{semester.name}' restored. {result['class_count']} classes are active again.",
        'class_count': result['class_count'],
    })


@login_required
def restore_class_view(request, class_id):
    """Restore a single archived class back to active."""
    from lms.services.semester_service import restore_class

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method.'}, status=405)

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Profile missing.'}, status=403)
    if profile.role != 'teacher':
        return JsonResponse({'status': 'error', 'message': 'Access restricted.'}, status=403)

    try:
        class_obj = Class.objects.get(id=class_id, teacher=request.user)
    except Class.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Class not found.'}, status=404)

    result = restore_class(class_obj, user=request.user)

    if not result['success']:
        return JsonResponse({'status': 'error', 'message': result['error']})

    message = f"Class '{class_obj.name}' restored to active."
    if result.get('semester_restored'):
        message += f" Semester '{result['semester_name']}' is now active again."

    return JsonResponse({
        'status': 'ok',
        'message': message,
        'semester_restored': result.get('semester_restored', False),
    })

@login_required
def class_settings(request, class_id):
    """
    Allow the teacher to configure behavior settings for a specific class.
    Fields: min_points_for_daily_test, points_per_conversion,
            bonus_per_conversion, max_bonus.
    """
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        messages.error(request, "Profile missing.")
        return redirect('dashboard')
    if profile.role != 'teacher':
        messages.error(request, "Only teachers can access.")
        return redirect('dashboard')

    try:
        class_obj = Class.objects.get(id=class_id, teacher=request.user)
    except Class.DoesNotExist:
        messages.error(request, "Class not found.")
        return redirect('dashboard')

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.method == 'POST':
        try:
            min_points = int(request.POST.get('min_points_for_daily_test', '0') or 0)
            points_per_conv = int(request.POST.get('points_per_conversion', '1') or 1)
            bonus_per_conv = int(request.POST.get('bonus_per_conversion', '1') or 1)
            max_bonus = int(request.POST.get('max_bonus', '0') or 0)
        except (ValueError, TypeError):
            msg = "All fields must be valid integers."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.error(request, msg)
            return redirect('class_settings', class_id=class_id)

        if min_points < 0:
            msg = "Minimum points for Daily Test cannot be negative."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.error(request, msg)
            return redirect('class_settings', class_id=class_id)
        if points_per_conv < 1:
            msg = "Points per conversion must be at least 1."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.error(request, msg)
            return redirect('class_settings', class_id=class_id)
        if bonus_per_conv < 1:
            msg = "Bonus per conversion must be at least 1."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.error(request, msg)
            return redirect('class_settings', class_id=class_id)
        if max_bonus < 0:
            msg = "Maximum bonus cannot be negative."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.error(request, msg)
            return redirect('class_settings', class_id=class_id)

        class_obj.min_points_for_daily_test = min_points
        class_obj.points_per_conversion = points_per_conv
        class_obj.bonus_per_conversion = bonus_per_conv
        class_obj.max_bonus = max_bonus
        class_obj.save()

        msg = f"Settings for {class_obj.name} updated successfully."
        if is_ajax:
            return JsonResponse({'status': 'ok', 'message': msg})
        messages.success(request, msg)
        return redirect('class_settings', class_id=class_id)

    context = {
        'class_obj': class_obj,
    }
    return render(request, 'lms/class_settings.html', context)

# ---------- Class Management ----------
@login_required
def add_class(request):
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Profile missing.'}, status=403)
        messages.error(request, "Profile missing.")
        return redirect('dashboard')
    if profile.role != 'teacher':
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Only teachers can access.'}, status=403)
        messages.error(request, "Only teachers can access.")
        return redirect('dashboard')

    semesters = Semester.objects.all()
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('is_ajax') == 'true'

    if request.method == 'POST':
        name = request.POST.get('name')
        semester_id = request.POST.get('semester')
        schedule = request.POST.get('schedule', '')

        if not name or not semester_id:
            msg = "Class name and semester are required."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.error(request, msg)
            return redirect('add_class')

        try:
            semester = Semester.objects.get(id=semester_id)
            Class.objects.create(
                name=name,
                teacher=request.user,
                semester=semester,
                schedule=schedule
            )
            msg = f"Class '{name}' created successfully."
            if is_ajax:
                return JsonResponse({'status': 'ok', 'message': msg})
            messages.success(request, msg)
            return redirect('dashboard')
        except Semester.DoesNotExist:
            msg = "Selected semester does not exist."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.error(request, msg)
            return redirect('add_class')

    context = {'semesters': semesters}
    return render(request, 'lms/add_class.html', context)


@login_required
def delete_class(request, class_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Profile missing.'}, status=403)
    if profile.role != 'teacher':
        return JsonResponse({'status': 'error', 'message': 'Only teachers can access.'}, status=403)

    try:
        class_obj = Class.objects.get(id=class_id, teacher=request.user)
        class_name = class_obj.name
        class_obj.delete()
        return JsonResponse({'status': 'ok', 'message': f"Class '{class_name}' has been deleted."})
    except Class.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Class not found.'}, status=404)


@login_required
def delete_student(request, student_id, class_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Profile missing.'}, status=403)
    if profile.role != 'teacher':
        return JsonResponse({'status': 'error', 'message': 'Only teachers can access.'}, status=403)

    try:
        class_obj = Class.objects.get(id=class_id, teacher=request.user)
        enrollment = Enrollment.objects.get(student_id=student_id, class_obj=class_obj)
        student_name = enrollment.student.name
        enrollment.delete()
        return JsonResponse({'status': 'ok', 'message': f"{student_name} has been removed from {class_obj.name}."})
    except (Class.DoesNotExist, Enrollment.DoesNotExist):
        return JsonResponse({'status': 'error', 'message': 'Student or class not found.'}, status=404)


# ---------- Charts ----------
@login_required
def charts(request):
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        messages.error(request, "Profile missing.")
        return redirect('dashboard')
    if profile.role != 'teacher':
        messages.error(request, "Only teachers can access.")
        return redirect('dashboard')

    all_classes = Class.objects.filter(teacher=request.user, is_archived=False)

    selected_class_id = request.GET.get('class_id')
    if selected_class_id == '':
        request.session.pop('selected_class_id', None)
        selected_class_id = None
    elif selected_class_id and selected_class_id.isdigit():
        request.session['selected_class_id'] = int(selected_class_id)
    elif 'selected_class_id' in request.session:
        selected_class_id = request.session['selected_class_id']
    else:
        selected_class_id = None

    selected_class_name = None
    if selected_class_id:
        try:
            cls = Class.objects.get(id=selected_class_id, teacher=request.user)
            selected_class_name = cls.name
        except Class.DoesNotExist:
            pass

    if request.GET.get('reset'):
        request.session.pop('selected_class_id', None)
        return redirect('charts')

    # ---------- Per-class averages ----------
    chart_class_names = []
    chart_class_avg_scores = []
    chart_components = {'academic': [], 'bonus': []}

    for cls in all_classes:
        enrollments = Enrollment.objects.filter(class_obj=cls, is_active=True).select_related('student')
        students = [e.student for e in enrollments]

        if not students:
            chart_class_names.append(cls.name)
            chart_class_avg_scores.append(0)
            for k in chart_components:
                chart_components[k].append(0)
            continue

        total_final = 0
        total_academic = 0
        total_bonus = 0
        count = 0

        for student in students:
            score_data = calculate_final_score(student, cls)
            total_final += score_data['final_score']
            total_academic += score_data['academic_average']
            total_bonus += score_data['bonus']
            count += 1

        if count > 0:
            chart_class_names.append(cls.name)
            chart_class_avg_scores.append(round(total_final / count, 1))
            chart_components['academic'].append(round(total_academic / count, 1))
            chart_components['bonus'].append(round(total_bonus / count, 1))
        else:
            chart_class_names.append(cls.name)
            chart_class_avg_scores.append(0)
            for k in chart_components:
                chart_components[k].append(0)

    # ---------- Histogram (per selected class) ----------
    score_ranges = ['<60', '60-70', '70-80', '80-90', '≥90']
    range_counts = [0, 0, 0, 0, 0]

    if selected_class_id:
        try:
            cls = Class.objects.get(id=selected_class_id, teacher=request.user)
            enrollments = Enrollment.objects.filter(class_obj=cls, is_active=True).select_related('student')

            for enrollment in enrollments:
                score_data = calculate_final_score(enrollment.student, cls)
                final = score_data['final_score']
                if final < 60:
                    range_counts[0] += 1
                elif final < 70:
                    range_counts[1] += 1
                elif final < 80:
                    range_counts[2] += 1
                elif final < 90:
                    range_counts[3] += 1
                else:
                    range_counts[4] += 1
        except Class.DoesNotExist:
            pass

    context = {
        'all_classes': all_classes,
        'selected_class_id': selected_class_id,
        'selected_class_name': selected_class_name,
        'chart_class_names': chart_class_names,
        'chart_class_avg_scores': chart_class_avg_scores,
        'chart_components': chart_components,
        'score_ranges': score_ranges,
        'range_counts': range_counts,
        'user': request.user,
    }
    return render(request, 'lms/charts.html', context)

def generate_ai_feedback_rule_based(
    student, class_obj, academic_avg, attendance_summary,
    total_positive, total_negative, available_points, bonus_earned,
    final_score, assessment_details, missing_count=0
):
    """Fallback rule-based feedback in Indonesian when AI is unavailable."""
    feedback = f"Laporan Perkembangan {student.name} - {class_obj.name}\n\n"
    feedback += (
        f"Rata-rata akademik: {academic_avg:.1f}. "
        f"Kehadiran: {attendance_summary}. "
        f"Skor akhir: {final_score}.\n\n"
    )
    feedback += "Detail nilai:\n"
    for d in assessment_details:
        feedback += f"- {d['name']} ({d['date']}): {d['percentage']}% ({d['score']}/{d['max_points']})"
        if d.get('notes'):
            feedback += f" — Catatan: {d['notes']}"
        feedback += "\n"

    if missing_count > 0:
        feedback += f"\nMasih ada {missing_count} asesmen yang belum memiliki nilai.\n"

    feedback += (
        f"\nPerilaku: poin positif {total_positive}, poin negatif {total_negative}, "
        f"poin tersedia {available_points}, bonus diperoleh +{bonus_earned}.\n\n"
    )

    if academic_avg >= 85:
        feedback += "Prestasi akademik sangat baik. "
    elif academic_avg >= 70:
        feedback += "Nilai akademik cukup baik. "
    else:
        feedback += "Nilai akademik perlu ditingkatkan. "

    if attendance_summary != "0/0":
        feedback += "Kehadiran tercatat dengan baik. "
    else:
        feedback += "Kehadiran belum tercatat. "

    if bonus_earned > 0:
        feedback += f"Ananda telah memperoleh bonus akademik +{bonus_earned} dari konversi poin perilaku. "

    if total_negative == 0:
        feedback += "Tidak ada catatan poin negatif — sikapnya sangat baik."
    elif total_negative <= 3:
        feedback += "Perilaku cukup baik."
    else:
        feedback += "Perilaku perlu perhatian lebih."

    feedback += "\n\nSaran: Diskusikan dengan guru untuk rencana perbaikan."
    return feedback

def generate_ai_feedback(student, class_obj):
    """Generate personalized AI feedback in Indonesian, using the new scoring system."""
    from lms.services.behavior_service import (
        calculate_behavior_status,
        calculate_final_score,
    )

    # ---------- Data gathering (via service) ----------
    score_data = calculate_final_score(student, class_obj)
    academic_avg = score_data['academic_average']
    bonus_earned = score_data['bonus']
    final_score = score_data['final_score']

    behavior_status = calculate_behavior_status(student, class_obj)
    total_positive = behavior_status['total_positive']
    total_negative = behavior_status['total_negative']
    available_points = behavior_status['available_points']
    daily_test_status = behavior_status['daily_test_status']
    points_needed_for_test = behavior_status['points_needed_for_test']

    # ---------- Assessment details ----------
    scores = Score.objects.filter(
        student=student, assessment__class_obj=class_obj
    ).select_related('assessment').order_by('assessment__date')

    assessment_details = []
    for sc in scores:
        ass = sc.assessment
        pct = (sc.points_earned / ass.max_points) * 100 if ass.max_points else 0
        assessment_details.append({
            'name': ass.name,
            'date': ass.date.strftime('%d %b %Y'),
            'score': sc.points_earned,
            'max_points': ass.max_points,
            'percentage': round(pct, 1),
            'notes': sc.notes or '',
        })

    all_assessments = Assessment.objects.filter(class_obj=class_obj)
    assessed_ids = set(scores.values_list('assessment_id', flat=True))
    missing_assessments = [a for a in all_assessments if a.id not in assessed_ids]
    missing_count = len(missing_assessments)

    # ---------- Attendance ----------
    attendance_records = AttendanceRecord.objects.filter(
        student=student, session__class_obj=class_obj
    )
    total_sessions = attendance_records.count()
    present_count = attendance_records.filter(
        status__in=['present', 'late', 'excused', 'sick']
    ).count()
    attendance_summary = f"{present_count}/{total_sessions}" if total_sessions > 0 else "0/0"
    attendance_percentage = (present_count / total_sessions * 100) if total_sessions > 0 else 0.0

    teacher_name = class_obj.teacher.get_full_name() or class_obj.teacher.username
    bulan_sekarang = datetime.now().strftime('%B %Y')

    # ---------- Academic status narrative ----------
    if all_assessments.count() > 0:
        academic_status = (
            f"Rata-rata nilai Ananda {student.name} dari seluruh {all_assessments.count()} "
            f"asesmen di kelas adalah {academic_avg:.1f}."
        )
        if missing_count > 0:
            academic_status += f" Namun, masih ada {missing_count} asesmen yang belum memiliki nilai."
    else:
        academic_status = "Belum ada asesmen di kelas ini."

    # ---------- Bonus narrative ----------
    if bonus_earned > 0:
        bonus_status = (
            f"Ananda telah memperoleh bonus akademik +{bonus_earned} dari konversi poin perilaku."
        )
    else:
        bonus_status = (
            f"Saat ini Ananda memiliki {available_points} poin perilaku yang tersedia. "
            f"Setiap {class_obj.points_per_conversion} poin dapat dikonversi menjadi "
            f"+{class_obj.bonus_per_conversion} bonus akademik."
        )

    # ---------- Daily Test narrative ----------
    if class_obj.min_points_for_daily_test > 0:
        if daily_test_status == 'ready':
            daily_test_status_text = (
                f"Ananda sudah memenuhi syarat untuk mengikuti Daily Test "
                f"(memiliki {available_points} poin, minimal {class_obj.min_points_for_daily_test})."
            )
        else:
            daily_test_status_text = (
                f"Untuk mengikuti Daily Test, Ananda masih membutuhkan "
                f"{points_needed_for_test} poin lagi."
            )
    else:
        daily_test_status_text = ""

    # ---------- Build prompt ----------
    prompt = f"""Anda adalah {teacher_name}, seorang guru yang hangat dan komunikatif. Tulislah SURAT PRIBADI untuk orang tua/wali dari Ananda {student.name} di kelas {class_obj.name}. Gunakan Bahasa Indonesia yang mengalir, santun, dan personal. Surat boleh terdiri dari beberapa paragraf pendek. (Saat ini adalah {bulan_sekarang}.)

**PENTING - SISTEM PENILAIAN BARU:**
- Skor akhir = Rata-rata Akademik MURNI + Bonus (dari konversi poin perilaku).
- Kehadiran dan poin perilaku TIDAK mempengaruhi rata-rata akademik.
- Poin perilaku hanya dipakai untuk: (1) syarat Daily Test, (2) konversi jadi bonus.

**Yang harus ada dalam surat:**
- Salam pembuka "Assalamualaikum Warahmatullahi Wabarakatuh".
- Apresiasi terhadap pencapaian atau karakter positif Ananda.
- Gambaran akademik: {academic_status}
- Info perilaku: Poin positif {total_positive}, poin negatif {total_negative}, poin tersedia {available_points}.
  *Jika poin positif tinggi (>=10), puji bahwa Ananda aktif dan disiplin.*
  *Jika poin negatif rendah (0-2), sampaikan sikapnya sudah baik.*
  *Jika poin negatif tinggi (>5), sampaikan dengan pengertian dan tawarkan strategi perbaikan.*
- Info bonus: {bonus_status}
- Info kehadiran: {attendance_summary} ({attendance_percentage:.1f}%).
- {daily_test_status_text}
- Skor akhir sebagai ringkasan: Skor Akhir: {final_score} (Rata-rata Akademik {academic_avg:.1f} + Bonus {bonus_earned})
- Motivasi dan harapan, termasuk solusi untuk siswa asrama: pentingnya komunikasi orang tua lewat telepon/video call, koordinasi dengan wali asrama.
- Kalimat penutup yang sopan, lalu "Hormat kami, {teacher_name}".

**Data pendukung (bisa dirujuk dengan ringkas):**
"""
    if assessment_details:
        for d in assessment_details:
            prompt += f"- {d['name']} ({d['date']}): {d['score']}/{d['max_points']} ({d['percentage']}%)\n"
    else:
        prompt += "(Belum ada nilai)\n"

    if missing_assessments:
        prompt += "\nBeberapa asesmen yang belum dinilai:\n"
        for a in missing_assessments:
            prompt += f"- {a.name} (maks {a.max_points} poin)\n"

    prompt += f"""
**Gaya penulisan:**
- Gunakan "saya" untuk guru, dan "Ananda {student.name}" untuk siswa.
- Jangan mengulang data mentah, ceritakan dengan bahasa yang enak dibaca.
- Jika ada area yang perlu ditingkatkan, sampaikan dengan optimis dan penuh pengertian.
- JANGAN menyebutkan rumus 60%/15%/15%/10% atau sistem lama apapun.
- Akhiri surat dengan nada positif yang menyemangati.

**Panjang surat:** sekitar 180-250 kata.
"""

    # ---------- Try AI ----------
    try:
        import ollama
        response = ollama.chat(
            model='gemma4:31b-cloud',
            messages=[
                {'role': 'system', 'content': 'Anda adalah guru yang ramah dan profesional.'},
                {'role': 'user', 'content': prompt}
            ],
            options={
                'temperature': 0.9,
                'num_predict': 500,
                'top_p': 0.9,
                'repeat_penalty': 1.1
            }
        )
        feedback = response['message']['content'].strip()

        if len(feedback) < 150:
            return generate_ai_feedback_rule_based(
                student, class_obj, academic_avg, attendance_summary,
                total_positive, total_negative, available_points, bonus_earned,
                final_score, assessment_details, missing_count
            )
        return feedback
    except ImportError:
        return generate_ai_feedback_rule_based(
            student, class_obj, academic_avg, attendance_summary,
            total_positive, total_negative, available_points, bonus_earned,
            final_score, assessment_details, missing_count
        )
    except Exception as e:
        print(f"Ollama error: {e}")
        return generate_ai_feedback_rule_based(
            student, class_obj, academic_avg, attendance_summary,
            total_positive, total_negative, available_points, bonus_earned,
            final_score, assessment_details, missing_count
        )@login_required
def student_feedback(request, student_id, class_id):
    from lms.services.behavior_service import (
        calculate_behavior_status,
        calculate_final_score,
    )

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        messages.error(request, "Profile missing.")
        return redirect('dashboard')
    if profile.role != 'teacher':
        messages.error(request, "Only teachers can access.")
        return redirect('dashboard')

    try:
        student = Student.objects.get(id=student_id)
        class_obj = Class.objects.get(id=class_id, teacher=request.user)
    except (Student.DoesNotExist, Class.DoesNotExist):
        messages.error(request, "Student or class not found.")
        return redirect('dashboard')

    feedback_obj, _ = StudentFeedback.objects.get_or_create(
        student=student, class_obj=class_obj, semester=class_obj.semester,
        defaults={'feedback_text': '', 'generated_by_ai': False}
    )

    # ---------- Data (via service) ----------
    score_data = calculate_final_score(student, class_obj)
    academic_avg = score_data['academic_average']
    bonus_earned = score_data['bonus']
    final_score = score_data['final_score']

    behavior_status = calculate_behavior_status(student, class_obj)

    # ---------- Assessments ----------
    all_assessments = Assessment.objects.filter(class_obj=class_obj)
    scores = Score.objects.filter(
        student=student, assessment__in=all_assessments
    ).select_related('assessment')

    assessment_details = []
    for sc in scores:
        ass = sc.assessment
        pct = (sc.points_earned / ass.max_points) * 100 if ass.max_points else 0
        assessment_details.append({
            'name': ass.name,
            'date': ass.date.strftime('%d %b %Y'),
            'score': sc.points_earned,
            'max_points': ass.max_points,
            'percentage': round(pct, 1),
            'notes': sc.notes,
        })

    assessed_ids = set(scores.values_list('assessment_id', flat=True))
    missing_assessments = [a for a in all_assessments if a.id not in assessed_ids]

    # ---------- Attendance ----------
    attendance_records = AttendanceRecord.objects.filter(
        student=student, session__class_obj=class_obj
    )
    total_sessions = attendance_records.count()
    present_count = attendance_records.filter(
        status__in=['present', 'late', 'excused', 'sick']
    ).count()
    attendance_percentage = (present_count / total_sessions * 100) if total_sessions > 0 else 0.0

    # ---------- POST handling ----------
    if request.method == 'POST':
        action = request.POST.get('action')
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

        if action == 'save_manual' or is_ajax:
            new_text = request.POST.get('feedback_text')
            if new_text is not None:
                feedback_obj.feedback_text = new_text
                feedback_obj.generated_by_ai = False
                feedback_obj.save()
                if is_ajax:
                    return JsonResponse({'status': 'ok'})
                messages.success(request, "Feedback saved.")
        elif action == 'generate_ai':
            new_text = generate_ai_feedback(student, class_obj)
            feedback_obj.feedback_text = new_text
            feedback_obj.generated_by_ai = True
            feedback_obj.save()
            messages.success(request, "AI feedback generated.")
        return redirect('student_feedback', student_id=student_id, class_id=class_id)

    context = {
        'student': student,
        'class_obj': class_obj,
        'feedback': feedback_obj,
        'academic_avg': round(academic_avg, 1),
        'attendance_percentage': round(attendance_percentage, 1),
        'total_positive': behavior_status['total_positive'],
        'total_negative': behavior_status['total_negative'],
        'available_points': behavior_status['available_points'],
        'bonus_earned': bonus_earned,
        'final_score': final_score,
        'assessment_details_json': json.dumps(assessment_details),
        'missing_assessments': missing_assessments,
    }
    return render(request, 'lms/student_feedback.html', context)

# ---------- PDF Generation ----------
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepTogether
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.graphics.shapes import Drawing, Line
import io, os, re, zipfile
from io import BytesIO

def _generate_report_pdf_buffer(student, class_obj):
    """
    Generate a polished PDF report for a student in a class.
    Uses Andhivie brand palette: Deep Red #9B1B30, Fox Orange #E07A3D.
    """
    from lms.services.behavior_service import (
        calculate_behavior_status,
        calculate_final_score,
    )

    # ---------- Data ----------
    score_data = calculate_final_score(student, class_obj)
    academic_avg = score_data['academic_average']
    bonus_earned = score_data['bonus']
    final_score = score_data['final_score']

    behavior_status = calculate_behavior_status(student, class_obj)
    total_positive = behavior_status['total_positive']
    total_negative = behavior_status['total_negative']
    available_points = behavior_status['available_points']

    scores = Score.objects.filter(
        student=student, assessment__class_obj=class_obj
    ).select_related('assessment').order_by('assessment__date')

    assessment_details = []
    for sc in scores:
        ass = sc.assessment
        pct = (sc.points_earned / ass.max_points) * 100 if ass.max_points else 0
        assessment_details.append({
            'name': ass.name,
            'type': ass.assessment_type.name if ass.assessment_type else '—',
            'date': ass.date.strftime('%d %b %Y'),
            'score': sc.points_earned,
            'max': ass.max_points,
            'percentage': round(pct, 1),
        })

    attendance_records = AttendanceRecord.objects.filter(
        student=student, session__class_obj=class_obj
    )
    total_sessions = attendance_records.count()
    present_count = attendance_records.filter(
        status__in=['present', 'late', 'excused', 'sick']
    ).count()
    attendance_summary = f"{present_count}/{total_sessions}" if total_sessions > 0 else "0/0"

    feedback_obj = StudentFeedback.objects.filter(
        student=student, class_obj=class_obj, semester=class_obj.semester
    ).first()
    feedback_text = feedback_obj.feedback_text if feedback_obj else "No feedback has been written yet."

    semester_name = class_obj.semester.name
    if "even" in semester_name.lower() or "genap" in semester_name.lower():
        semester_label = "Even Semester"
    elif "odd" in semester_name.lower() or "ganjil" in semester_name.lower():
        semester_label = "Odd Semester"
    else:
        semester_label = semester_name

    def fmt_num(n):
        if isinstance(n, float) and n.is_integer():
            return str(int(n))
        if isinstance(n, int):
            return str(n)
        return f"{n:.1f}"

    def fmt_pos(n):
        return f"+{n}" if n > 0 else "0"

    def fmt_neg(n):
        return f"-{n}" if n > 0 else "0"

    # ---------- Colors ----------
    DEEP_RED = colors.HexColor('#9B1B30')
    FOX_ORANGE = colors.HexColor('#E07A3D')
    CHARCOAL = colors.HexColor('#1F2937')
    WARM_GRAY = colors.HexColor('#6B7280')
    SOFT_CREAM = colors.HexColor('#FDF8F4')
    SOFT_GRAY = colors.HexColor('#F3F4F6')
    BORDER_GRAY = colors.HexColor('#E5E7EB')
    GREEN = colors.HexColor('#059669')
    RED = colors.HexColor('#DC2626')

    # ---------- Document ----------
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=1.4*cm, leftMargin=1.4*cm,
        topMargin=1.2*cm, bottomMargin=1.8*cm
    )
    story = []
    styles = getSampleStyleSheet()
    base_normal = styles['Normal']

    # ---------- Styles ----------
    title_style = ParagraphStyle(
        'Title', parent=styles['Heading1'],
        fontName='Helvetica-Bold', fontSize=22,
        textColor=DEEP_RED, alignment=TA_CENTER, spaceAfter=2, leading=26
    )
    subtitle_style = ParagraphStyle(
        'Subtitle', parent=base_normal, fontName='Helvetica',
        fontSize=10, textColor=WARM_GRAY, alignment=TA_CENTER, spaceAfter=2
    )
    heading_style = ParagraphStyle(
        'Heading', parent=styles['Heading2'],
        fontName='Helvetica-Bold', fontSize=11.5,
        textColor=DEEP_RED, spaceBefore=12, spaceAfter=7,
        keepWithNext=True
    )
    normal_style = ParagraphStyle(
        'Normal', parent=base_normal, fontName='Helvetica',
        fontSize=9.5, leading=13, textColor=CHARCOAL, spaceAfter=5,
        allowWidows=0, allowOrphans=0
    )
    info_label_style = ParagraphStyle(
        'InfoLabel', parent=base_normal, fontName='Helvetica-Bold',
        fontSize=7.5, textColor=WARM_GRAY, alignment=TA_CENTER, spaceAfter=3
    )
    info_value_style = ParagraphStyle(
        'InfoValue', parent=base_normal, fontName='Helvetica-Bold',
        fontSize=11, textColor=CHARCOAL, alignment=TA_CENTER
    )
    metric_label_style = ParagraphStyle(
        'MetricLabel', parent=base_normal, fontName='Helvetica-Bold',
        fontSize=7, textColor=WARM_GRAY, alignment=TA_CENTER, leading=9
    )
    metric_value_style = ParagraphStyle(
        'MetricValue', parent=base_normal, fontName='Helvetica-Bold',
        fontSize=16, textColor=CHARCOAL, alignment=TA_CENTER, leading=20
    )
    bullet_style = ParagraphStyle(
        'Bullet', parent=normal_style, leftIndent=15,
        fontSize=9, leading=12.5, spaceAfter=3
    )
    right_header_style = ParagraphStyle(
        'RightHeader', parent=base_normal, fontName='Helvetica',
        fontSize=9, textColor=WARM_GRAY, alignment=TA_RIGHT, spaceAfter=5
    )

    # ============================================================
    # HEADER
    # ============================================================
    story.append(Paragraph(
        f"{class_obj.name} &nbsp;&nbsp;·&nbsp;&nbsp; {semester_label}",
        right_header_style
    ))

    logo_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'logo.png')
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=0.75*inch, height=0.75*inch)
        logo.hAlign = 'CENTER'
        story.append(logo)
        story.append(Spacer(1, 0.05*inch))

    story.append(Paragraph("STUDENT PROGRESS REPORT", title_style))
    story.append(Paragraph(
        "SMP Al-Izzah Leadership School Batu",
        subtitle_style
    ))

    story.append(Spacer(1, 0.08*inch))
    deco = Drawing(510, 5)
    deco.add(Line(80, 2.5, 430, 2.5, strokeColor=DEEP_RED, strokeWidth=2.5))
    deco.hAlign = 'CENTER'
    story.append(deco)
    story.append(Spacer(1, 0.15*inch))

    # ============================================================
    # STUDENT INFO
    # ============================================================
    info_rows = [
        [
            Paragraph("STUDENT NAME", info_label_style),
            Paragraph("CLASS", info_label_style),
            Paragraph("TEACHER", info_label_style),
        ],
        [
            Paragraph(student.name, info_value_style),
            Paragraph(class_obj.name, info_value_style),
            Paragraph(
                class_obj.teacher.get_full_name() or class_obj.teacher.username,
                info_value_style
            ),
        ],
    ]
    info_table = Table(info_rows, colWidths=[doc.width/3.0]*3)
    info_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 0), (-1, -1), SOFT_CREAM),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER_GRAY),
        ('LINEAFTER', (0, 0), (0, -1), 0.5, BORDER_GRAY),
        ('LINEAFTER', (1, 0), (1, -1), 0.5, BORDER_GRAY),
        ('LINEABOVE', (0, 0), (-1, 0), 2.5, DEEP_RED),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 3),
        ('TOPPADDING', (0, 1), (-1, 1), 2),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 10),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.16*inch))

    # ============================================================
    # ACHIEVEMENT SUMMARY
    # ============================================================
    story.append(Paragraph("Achievement Summary", heading_style))

    metrics = [
        ("ACADEMIC AVG.", fmt_num(academic_avg), CHARCOAL),
        ("ATTENDANCE", attendance_summary, CHARCOAL),
        ("FINAL SCORE", fmt_num(final_score), FOX_ORANGE),
        ("POSITIVE PTS.", fmt_pos(total_positive), GREEN),
        ("NEGATIVE PTS.", fmt_neg(total_negative), RED),
        ("BONUS EARNED", fmt_pos(bonus_earned), FOX_ORANGE),
    ]

    def make_metric_card(label, value, value_color):
        value_style = ParagraphStyle(
            f'MV_{label}', parent=metric_value_style, textColor=value_color
        )
        card = Table(
            [
                [Paragraph(label, metric_label_style)],
                [Paragraph(value, value_style)],
            ],
            colWidths=[doc.width/3.0 - 12]
        )
        card.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (-1, -1), SOFT_CREAM),
            ('BOX', (0, 0), (-1, -1), 0.5, BORDER_GRAY),
            ('LINEABOVE', (0, 0), (-1, 0), 3, value_color),
            ('TOPPADDING', (0, 0), (-1, 0), 7),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 1),
            ('TOPPADDING', (0, 1), (-1, 1), 1),
            ('BOTTOMPADDING', (0, 1), (-1, 1), 9),
        ]))
        return card

    for row_start in range(0, 6, 3):
        cells = []
        for i in range(row_start, row_start + 3):
            label, value, color = metrics[i]
            cells.append(make_metric_card(label, value, color))
        row_table = Table([cells], colWidths=[doc.width/3.0]*3)
        row_table.setStyle(TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(row_table)

    story.append(Spacer(1, 0.14*inch))

    # ============================================================
    # ASSESSMENT DETAILS
    # ============================================================
    story.append(Paragraph("Assessment Details", heading_style))

    if assessment_details:
        header = ["No.", "Topic", "Type", "Date", "Score", "%"]
        ass_data = [header]
        for i, d in enumerate(assessment_details, 1):
            ass_data.append([
                str(i),
                Paragraph(d['name'], normal_style),
                Paragraph(d['type'], normal_style),
                d['date'],
                f"{fmt_num(d['score'])}/{fmt_num(d['max'])}",
                f"{fmt_num(d['percentage'])}%",
            ])

        ass_table = Table(
            ass_data,
            colWidths=[26, 155, 95, 60, 55, 45],
            repeatRows=1
        )
        ass_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BACKGROUND', (0, 0), (-1, 0), DEEP_RED),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.4, BORDER_GRAY),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, SOFT_CREAM]),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(ass_table)
        story.append(Spacer(1, 0.06*inch))
        story.append(Paragraph(
            "<i>% = Achievement percentage against the maximum score.</i>",
            ParagraphStyle('Note', parent=normal_style, fontSize=7.5, textColor=WARM_GRAY)
        ))
    else:
        empty_table = Table(
            [[Paragraph(
                "<i>No assessments have been recorded for this student yet.</i>",
                ParagraphStyle('Empty', parent=normal_style,
                               alignment=TA_CENTER, textColor=WARM_GRAY)
            )]],
            colWidths=[doc.width]
        )
        empty_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), SOFT_GRAY),
            ('BOX', (0, 0), (-1, -1), 0.5, BORDER_GRAY),
            ('TOPPADDING', (0, 0), (-1, -1), 14),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
        ]))
        story.append(empty_table)

    story.append(Spacer(1, 0.16*inch))

    # ============================================================
    # TEACHER NOTES / FEEDBACK
    # ============================================================
    story.append(Paragraph("Teacher Notes / Feedback", heading_style))

    clean_feedback = re.sub(r'\*\*(.*?)\*\*', r'\1', feedback_text)
    clean_feedback = re.sub(r'\*(.*?)\*', r'\1', clean_feedback)
    clean_feedback = clean_feedback.replace('#', '')
    feedback_paragraphs = [p.strip() for p in clean_feedback.split('\n') if p.strip()]
    if not feedback_paragraphs:
        feedback_paragraphs = ["No feedback has been written yet."]

    feedback_content = []
    for i, para in enumerate(feedback_paragraphs):
        feedback_content.append(Paragraph(para, normal_style))
        if i < len(feedback_paragraphs) - 1:
            feedback_content.append(Spacer(1, 0.04*inch))

    feedback_table = Table([[feedback_content]], colWidths=[doc.width])
    feedback_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), SOFT_CREAM),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER_GRAY),
        ('LINEBEFORE', (0, 0), (0, -1), 3.5, FOX_ORANGE),
        ('TOPPADDING', (0, 0), (-1, -1), 13),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 13),
        ('LEFTPADDING', (0, 0), (-1, -1), 16),
        ('RIGHTPADDING', (0, 0), (-1, -1), 16),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(feedback_table)
    story.append(Spacer(1, 0.16*inch))

    # ============================================================
    # BEHAVIOR POINT SYSTEM
    # ============================================================
    story.append(Paragraph("How Behavior Points Work", heading_style))

    behavior_content = []
    behavior_content.append(Paragraph(
        "<b>Point Scale</b> &nbsp;&nbsp;&nbsp;"
        "<font color='#059669'>Positive: +1, +2, +3</font> &nbsp;&nbsp;|&nbsp;&nbsp; "
        "<font color='#DC2626'>Negative: -1, -2, -3</font>",
        normal_style
    ))
    behavior_content.append(Spacer(1, 0.05*inch))

    behavior_content.append(Paragraph(
        "<b>Final Score Formula</b>",
        ParagraphStyle('Sub', parent=normal_style, fontSize=9.5, spaceAfter=4, textColor=DEEP_RED)
    ))
    behavior_content.append(Paragraph(
        "&bull; The academic average comes from assessment scores only.",
        bullet_style
    ))
    behavior_content.append(Paragraph(
        "&bull; Attendance and behavior points do <b>not</b> change the academic average.",
        bullet_style
    ))
    behavior_content.append(Paragraph(
        f"&bull; Every <b>{class_obj.points_per_conversion} available points</b> "
        f"can be converted into <b>+{class_obj.bonus_per_conversion} academic bonus</b> "
        f"(maximum <b>+{class_obj.max_bonus}</b> per semester).",
        bullet_style
    ))
    behavior_content.append(Paragraph(
        f"&bull; Current available points: <b>{available_points}</b> "
        f"&nbsp;&nbsp;|&nbsp;&nbsp; Bonus earned so far: <b>+{bonus_earned}</b>",
        bullet_style
    ))
    behavior_content.append(Spacer(1, 0.05*inch))

    if class_obj.min_points_for_daily_test > 0:
        behavior_content.append(Paragraph(
            f"<b>Daily Test Requirement</b> &mdash; Students need at least "
            f"<b>{class_obj.min_points_for_daily_test} available points</b> "
            f"before taking a Daily Test.",
            normal_style
        ))
    else:
        behavior_content.append(Paragraph(
            "<b>Daily Test Requirement</b> &mdash; Not enforced for this class.",
            normal_style
        ))

    behavior_content.append(Spacer(1, 0.05*inch))
    behavior_content.append(Paragraph(
        "<i>This system records character, not judges it. "
        "Students are always given the chance to improve through positive replacement actions.</i>",
        ParagraphStyle('CoreNote', parent=normal_style,
                       fontSize=8.5, textColor=WARM_GRAY)
    ))

    behavior_table = Table([[behavior_content]], colWidths=[doc.width])
    behavior_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER_GRAY),
        ('LINEBEFORE', (0, 0), (0, -1), 3.5, DEEP_RED),
        ('TOPPADDING', (0, 0), (-1, -1), 13),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 13),
        ('LEFTPADDING', (0, 0), (-1, -1), 16),
        ('RIGHTPADDING', (0, 0), (-1, -1), 16),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(behavior_table)

    # ============================================================
    # SIGNATURE (compact + keep-together with behavior table)
    # ============================================================
    story.append(Spacer(1, 0.18*inch))

    signature_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'sig.png')
    full_name = class_obj.teacher.get_full_name() or class_obj.teacher.username
    teacher_name = full_name.split(',')[0].strip()

    center_style = ParagraphStyle(
        'CenterStyle', parent=normal_style,
        alignment=TA_CENTER, fontSize=10, leading=13
    )

    right_content = []
    right_content.append(Paragraph(
        "<font color='#6B7280' size='8'>Teacher</font>",
        center_style
    ))
    right_content.append(Spacer(1, 0.05*inch))

    if os.path.exists(signature_path):
        signature_img = Image(signature_path, width=1.2*inch, height=0.45*inch)
        signature_img.hAlign = 'CENTER'
        right_content.append(signature_img)
        right_content.append(Spacer(1, 0.04*inch))
    else:
        right_content.append(Spacer(1, 0.4*inch))

    right_content.append(Paragraph(
        f"<b>{teacher_name}</b>",
        ParagraphStyle('TeacherName', parent=center_style, textColor=DEEP_RED, fontSize=11)
    ))

    signature_data = [[Paragraph("", normal_style), right_content]]
    signature_table = Table(signature_data, colWidths=[doc.width*0.5, doc.width*0.5])
    signature_table.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('VALIGN', (1, 0), (1, 0), 'TOP'),
        ('LEFTPADDING', (1, 0), (1, 0), 0),
        ('RIGHTPADDING', (1, 0), (1, 0), 0),
        ('TOPPADDING', (1, 0), (1, 0), 5),
    ]))

    # Keep signature together as one block (won't split across pages)
    story.append(KeepTogether(signature_table))

    # ============================================================
    # BUILD WITH PAGE FOOTER
    # ============================================================
    def add_page_footer(canvas, doc_obj):
        canvas.saveState()
        canvas.setStrokeColor(BORDER_GRAY)
        canvas.setLineWidth(0.5)
        canvas.line(1.4*cm, 1.2*cm, A4[0] - 1.4*cm, 1.2*cm)

        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(WARM_GRAY)
        canvas.drawString(
            1.4*cm, 0.95*cm,
            f"Printed on {timezone.now().strftime('%d %B %Y, %H:%M')}"
        )
        canvas.drawCentredString(
            A4[0] / 2.0, 0.95*cm,
            "Classroom LMS by Andhivie"
        )
        canvas.drawRightString(
            A4[0] - 1.4*cm, 0.95*cm,
            f"Page {doc_obj.page}"
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=add_page_footer, onLaterPages=add_page_footer)
    buffer.seek(0)
    return buffer

@login_required
def generate_report_pdf(request, student_id, class_id):
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        messages.error(request, "Profile missing.")
        return redirect('dashboard')
    if profile.role != 'teacher':
        messages.error(request, "Only teachers can access.")
        return redirect('dashboard')
    try:
        student = Student.objects.get(id=student_id)
        class_obj = Class.objects.get(id=class_id, teacher=request.user)
    except (Student.DoesNotExist, Class.DoesNotExist):
        messages.error(request, "Student or class not found.")
        return redirect('dashboard')
    buffer = _generate_report_pdf_buffer(student, class_obj)
    pdf = buffer.getvalue()
    buffer.close()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Rapor_{student.name}_{class_obj.name}.pdf"'
    return response


@login_required
def download_class_reports_zip(request, class_id):
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        messages.error(request, "Profile missing.")
        return redirect('dashboard')
    if profile.role != 'teacher':
        messages.error(request, "Only teachers can access.")
        return redirect('dashboard')
    try:
        class_obj = Class.objects.get(id=class_id, teacher=request.user)
    except Class.DoesNotExist:
        messages.error(request, "Class not found.")
        return redirect('dashboard')
    enrollments = Enrollment.objects.filter(class_obj=class_obj, is_active=True).select_related('student')
    students = [e.student for e in enrollments]
    if not students:
        messages.warning(request, "Tidak ada siswa di kelas ini.")
        return redirect('dashboard')
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for student in students:
            pdf_buffer = _generate_report_pdf_buffer(student, class_obj)
            filename = f"Rapor_{student.name.replace(' ', '_')}_{class_obj.name}.pdf"
            zip_file.writestr(filename, pdf_buffer.getvalue())
            pdf_buffer.close()
    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="Rapor_{class_obj.name}.zip"'
    return response


# ---------- Export to Excel ----------
@login_required
def export_class_to_excel(request, class_id):
    """
    Export class data to Excel with the new scoring system:
      - Pure Academic Average (from assessments only)
      - Bonus (from behavior conversions)
      - Final Score = Academic + Bonus (capped at 100)
      - Behavior points and attendance shown as info only, not in final score
    """
    from lms.services.behavior_service import (
        calculate_behavior_status,
        calculate_final_score,
    )

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        messages.error(request, "Profile missing.")
        return redirect('dashboard')
    if profile.role != 'teacher':
        messages.error(request, "Only teachers can access.")
        return redirect('dashboard')

    try:
        class_obj = Class.objects.get(id=class_id, teacher=request.user)
    except Class.DoesNotExist:
        messages.error(request, "Class not found.")
        return redirect('dashboard')

    enrollments = (
        Enrollment.objects
        .filter(class_obj=class_obj, is_active=True)
        .select_related('student')
        .order_by('student__name')
    )
    students = [e.student for e in enrollments]

    def fmt_num(n):
        """Format number: integers without decimals, others 1 decimal."""
        if isinstance(n, float) and n.is_integer():
            return int(n)
        if isinstance(n, int):
            return n
        return round(n, 1)

    # Per-assessment scores cache
    assessments = list(
        Assessment.objects.filter(class_obj=class_obj).order_by('date')
    )
    assessment_scores = {}
    if assessments:
        scores_qs = Score.objects.filter(
            student__in=students, assessment__in=assessments
        ).select_related('assessment')
        for sc in scores_qs:
            key = (sc.student_id, sc.assessment_id)
            assessment_scores[key] = f"{fmt_num(sc.points_earned)}/{fmt_num(sc.assessment.max_points)}"

    # Attendance cache (display only)
    attendance_map = {}
    if students:
        attendance_qs = AttendanceRecord.objects.filter(
            student__in=students, session__class_obj=class_obj
        )
        for rec in attendance_qs:
            sid = rec.student_id
            if sid not in attendance_map:
                attendance_map[sid] = {'total': 0, 'present': 0}
            attendance_map[sid]['total'] += 1
            if rec.status in ['present', 'late', 'excused', 'sick']:
                attendance_map[sid]['present'] += 1

    # Build rows
    data = []
    for idx, student in enumerate(students, 1):
        status = calculate_behavior_status(student, class_obj)
        score_data = calculate_final_score(student, class_obj)

        att = attendance_map.get(student.id, {'total': 0, 'present': 0})
        att_summary = f"{att['present']}/{att['total']}" if att['total'] > 0 else "0/0"

        row = {
            'No': idx,
            'Student Name': student.name,
            'Academic Average': fmt_num(score_data['academic_average']),
            'Attendance': att_summary,
            'Positive Points': status['total_positive'],
            'Negative Points': status['total_negative'],
            'Available Points': status['available_points'],
            'Bonus Earned': score_data['bonus'],
            'Final Score': score_data['final_score'],
        }
        for ass in assessments:
            row[ass.name] = assessment_scores.get((student.id, ass.id), '-')
        data.append(row)

    # ---------- Build Excel ----------
    try:
        import pandas as pd
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        messages.error(
            request,
            "Excel export requires pandas and openpyxl. Install with: pip install pandas openpyxl"
        )
        return redirect('dashboard')

    df = pd.DataFrame(data)
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    safe_class_name = class_obj.name.replace(' ', '_').replace('/', '-')
    response['Content-Disposition'] = f'attachment; filename="{safe_class_name}_data.xlsx"'

    with pd.ExcelWriter(response, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Class Data', index=False)
        workbook = writer.book
        worksheet = writer.sheets['Class Data']

        # Styles
        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_fill = PatternFill(start_color="9B1B30", end_color="9B1B30", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        even_fill = PatternFill(start_color="FDF8F4", end_color="FDF8F4", fill_type="solid")
        thin_border = Border(
            left=Side(style='thin', color='E5E7EB'),
            right=Side(style='thin', color='E5E7EB'),
            top=Side(style='thin', color='E5E7EB'),
            bottom=Side(style='thin', color='E5E7EB'),
        )

        # Header row
        for col_idx, col_name in enumerate(df.columns, 1):
            cell = worksheet.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            cell.border = thin_border

        # Data rows
        center_cols = {
            'No', 'Academic Average', 'Attendance',
            'Positive Points', 'Negative Points',
            'Available Points', 'Bonus Earned', 'Final Score',
        }
        for row_idx in range(2, len(df) + 2):
            for col_idx, col_name in enumerate(df.columns, 1):
                cell = worksheet.cell(row=row_idx, column=col_idx)
                cell.border = thin_border
                if row_idx % 2 == 0:
                    cell.fill = even_fill

                if col_name == 'Student Name':
                    cell.alignment = Alignment(horizontal="left", vertical="center")
                elif col_name in center_cols:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                else:
                    cell.alignment = Alignment(horizontal="center", vertical="center")

        # Column widths
        for col_idx, col_name in enumerate(df.columns, 1):
            max_length = len(str(col_name))
            for row_idx in range(2, len(df) + 2):
                val = worksheet.cell(row=row_idx, column=col_idx).value
                if val is not None:
                    max_length = max(max_length, len(str(val)))
            adjusted = min(max_length + 3, 40)
            worksheet.column_dimensions[get_column_letter(col_idx)].width = adjusted

        worksheet.row_dimensions[1].height = 26

        # Freeze top row
        worksheet.freeze_panes = 'A2'

        # Footer
        footer_row = len(df) + 3
        footer_lines = [
            f"Class: {class_obj.name} ({class_obj.semester.name})",
            f"Teacher: {request.user.get_full_name() or request.user.username}",
            f"Exported: {datetime.now().strftime('%d %B %Y, %H:%M:%S')}",
            f"Total Students: {len(students)}",
            "",
            "Formula: Final Score = Pure Academic Average + Bonus (capped at 100).",
            "Attendance and behavior points do not affect the academic score.",
        ]
        for i, line in enumerate(footer_lines):
            cell = worksheet.cell(row=footer_row + i, column=1, value=line)
            cell.font = Font(italic=True, color="6B7280", size=9)
            cell.alignment = Alignment(horizontal="left", vertical="center")

    return response

# ---------- Reset Class Data ----------
@login_required
def reset_class_data(request, class_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Profile missing.'}, status=403)
    if profile.role != 'teacher':
        return JsonResponse({'status': 'error', 'message': 'Only teachers can access.'}, status=403)
    try:
        class_obj = Class.objects.get(id=class_id, teacher=request.user)
    except Class.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Class not found.'}, status=404)

    delete_students = request.POST.get('delete_students', 'false').lower() == 'true'

    # Create a backup before destructive operation
    from lms.services.backup_service import create_backup
    create_backup(reason='pre_reset_class', rotate=False)

    delete_students = request.POST.get('delete_students', 'false').lower() == 'true'
    
    AttendanceSession.objects.filter(class_obj=class_obj).delete()
    assessments = Assessment.objects.filter(class_obj=class_obj)
    Score.objects.filter(assessment__in=assessments).delete()
    assessments.delete()
    student_ids = Enrollment.objects.filter(class_obj=class_obj, is_active=True).values_list('student', flat=True)
    BehaviorEntry.objects.filter(student__in=student_ids).delete()
    StudentFeedback.objects.filter(class_obj=class_obj).delete()

    if delete_students:
        Enrollment.objects.filter(class_obj=class_obj).delete()
        message = f"All data and students have been removed from class '{class_obj.name}'."
    else:
        message = f"All data for class '{class_obj.name}' has been reset. Students remain enrolled."

    return JsonResponse({'status': 'ok', 'message': message})


@login_required
def clear_attendance(request, class_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Profile missing.'}, status=403)
    if profile.role != 'teacher':
        return JsonResponse({'status': 'error', 'message': 'Only teachers can access.'}, status=403)

    try:
        class_obj = Class.objects.get(id=class_id, teacher=request.user)
    except Class.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Class not found.'}, status=404)

    date_str = request.POST.get('date')
    if not date_str:
        return JsonResponse({'status': 'error', 'message': 'Date parameter missing.'}, status=400)

    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'status': 'error', 'message': 'Invalid date format.'}, status=400)

    try:
        session = AttendanceSession.objects.get(class_obj=class_obj, date=selected_date)
    except AttendanceSession.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'No attendance session found for this date.'}, status=404)

    AttendanceRecord.objects.filter(session=session).delete()
    session.delete()

    message = f"Attendance for {class_obj.name} on {selected_date.strftime('%A, %d %B %Y')} has been cleared."
    return JsonResponse({'status': 'ok', 'message': message})


@login_required
def student_attendance_history(request, class_id):
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        messages.error(request, "Profile missing.")
        return redirect('dashboard')
    if profile.role != 'teacher':
        messages.error(request, "Only teachers can access.")
        return redirect('dashboard')

    try:
        class_obj = Class.objects.get(id=class_id, teacher=request.user)
    except Class.DoesNotExist:
        messages.error(request, "Class not found.")
        return redirect('dashboard')

    enrollments = Enrollment.objects.filter(
        class_obj=class_obj, is_active=True
    ).select_related('student').order_by('student__name')

    sessions = AttendanceSession.objects.filter(
        class_obj=class_obj,
        records__isnull=False        # hanya sesi yang memiliki setidaknya satu record kehadiran
    ).distinct().order_by('-date')
    
    student_attendance = []
    for enrollment in enrollments:
        student = enrollment.student
        records = AttendanceRecord.objects.filter(
            student=student, session__in=sessions
        ).select_related('session')
        status_dict = {rec.session_id: rec.get_status_display() for rec in records}
        
        attendance_row = {
            'student': student,
            'statuses': [status_dict.get(session.id, '—') for session in sessions],
        }
        student_attendance.append(attendance_row)

    context = {
        'class_obj': class_obj,
        'sessions': sessions,
        'student_attendance': student_attendance,
    }
    return render(request, 'lms/student_attendance_history.html', context)

import os
from django.conf import settings
from django.core.files.storage import default_storage

@login_required
def backup_database(request):
    """
    Download a SQLite backup AND save a copy to the backups/ folder.
    Uses copyfile (not copy2) so the backup file gets a fresh mtime.
    Supports ?ajax=true to return JSON instead of downloading.
    """
    import shutil
    import time as _time

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Profile missing.'}, status=403)
    if profile.role != 'teacher':
        return JsonResponse({'status': 'error', 'message': 'Access restricted.'}, status=403)

    db_path = str(settings.DATABASES['default']['NAME'])
    if not os.path.isabs(db_path):
        db_path = os.path.abspath(db_path)

    # ---- 1. Validasi file yang diupload ----
    temp_path = db_path + '.restore_temp'
    try:
        with open(temp_path, 'wb+') as dest:
            for chunk in uploaded_file.chunks():
                dest.write(chunk)

        # Validate as SQLite
        conn = sqlite3.connect(temp_path)
        conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        conn.close()
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        return JsonResponse({
            'status': 'error',
            'message': f'Uploaded file is not a valid SQLite database: {str(e)}'
        })

    # ---- 2. Pre-restore backup via service ----
    from lms.services.backup_service import create_backup
    backup_result = create_backup(reason='pre_restore', rotate=False)
    backup_filename = backup_result.get('filename') if backup_result.get('success') else None
    if not backup_result.get('success'):
        print(f"Warning: Could not create backup before restore: {backup_result.get('error')}")

    # ---- 3. Close ALL Django DB connections so the file is not locked ----
    from django.db import connections
    for conn in connections.all():
        try:
            conn.close()
        except Exception:
            pass

    # ---- 4. Replace the database file ----
    # On Windows, os.replace requires the target file to not be open.
    # If replace fails, fall back to copyfile + remove.
    try:
        try:
            os.replace(temp_path, db_path)
        except OSError:
            # Fallback: copy content over existing file
            import shutil
            shutil.copyfile(temp_path, db_path)
            try:
                os.remove(temp_path)
            except OSError:
                pass
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        return JsonResponse({
            'status': 'error',
            'message': (
                f'Failed to replace database: {str(e)}. '
                'Try stopping the server, replacing db.sqlite3 manually, '
                'then start the server again.'
            )
        })

    return JsonResponse({
        'status': 'ok',
        'message': 'Database restored successfully. Please restart the server manually to apply changes fully.',
        'backup_created': backup_filename,
    })

import os
import shutil
import sqlite3
from datetime import datetime
from django.conf import settings
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

@login_required
def restore_database(request):
    """
    Restore database by copying content from uploaded file into the live DB.
    Uses SQLite's native backup API — safe on Windows (no file replacement).
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Method not allowed.'}, status=405)

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Profile missing.'}, status=403)
    if profile.role != 'teacher':
        return JsonResponse({'status': 'error', 'message': 'Access restricted.'}, status=403)

    uploaded_file = request.FILES.get('database')
    if not uploaded_file:
        return JsonResponse({'status': 'error', 'message': 'No file uploaded.'})

    if not uploaded_file.name.endswith('.sqlite3'):
        return JsonResponse({'status': 'error', 'message': 'Invalid file format. Must be .sqlite3'})

    db_path = str(settings.DATABASES['default']['NAME'])
    if not os.path.isabs(db_path):
        db_path = os.path.abspath(db_path)

    # ---- 1. Save uploaded file to temp and validate as SQLite ----
    temp_path = db_path + '.upload_temp'
    try:
        with open(temp_path, 'wb+') as dest:
            for chunk in uploaded_file.chunks():
                dest.write(chunk)

        # Validate: can it be opened as SQLite and has tables?
        test_conn = sqlite3.connect(temp_path)
        cur = test_conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cur.fetchall()
        test_conn.close()
        if not tables:
            raise ValueError('Uploaded file contains no tables.')
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        return JsonResponse({
            'status': 'error',
            'message': f'Uploaded file is not a valid SQLite database: {str(e)}'
        })

    # ---- 2. Pre-restore backup via service ----
    from lms.services.backup_service import create_backup
    backup_result = create_backup(reason='pre_restore', rotate=False)
    backup_filename = backup_result.get('filename') if backup_result.get('success') else None
    if not backup_result.get('success'):
        print(f"Warning: Could not create backup before restore: {backup_result.get('error')}")

    # ---- 3. Close Django connections to release any locks ----
    from django.db import connections
    for conn in connections.all():
        try:
            conn.close()
        except Exception:
            pass

    # ---- 4. Write contents of uploaded file INTO live DB via SQLite backup API ----
    # This does NOT replace the file, so no Windows file-lock issue.
    try:
        src = sqlite3.connect(temp_path)   # uploaded backup
        dst = sqlite3.connect(db_path)     # live database
        with dst:
            src.backup(dst)                # copy everything
        dst.close()
        src.close()
    except Exception as e:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass
        return JsonResponse({
            'status': 'error',
            'message': f'Restore failed: {str(e)}'
        })
    finally:
        # Clean up uploaded temp file
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass

    return JsonResponse({
        'status': 'ok',
        'message': 'Database restored successfully. Please restart the server manually to apply changes fully.',
        'backup_created': backup_filename,
    })
    
from django.core.files.uploadedfile import InMemoryUploadedFile
import io

@login_required
def upload_profile_picture(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Method not allowed.'}, status=405)

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Profile missing.'}, status=403)

    uploaded_file = request.FILES.get('profile_picture')
    if not uploaded_file:
        return JsonResponse({'status': 'error', 'message': 'No file uploaded.'})

        # Size validation (max 2 MB)
    if uploaded_file.size > 2 * 1024 * 1024:
        return JsonResponse({'status': 'error', 'message': 'File is too large. Maximum size is 2 MB.'})

    # Validate with PIL
    try:
        from PIL import Image as PILImage
        img = PILImage.open(uploaded_file)
        img.verify()
        uploaded_file.seek(0)
        img = PILImage.open(uploaded_file)
        if img.format not in ('JPEG', 'PNG', 'WEBP'):
            return JsonResponse({'status': 'error', 'message': 'Image format must be JPG, PNG, or WEBP.'})
    except ImportError:
        return JsonResponse({'status': 'error', 'message': 'Server does not support image processing (Pillow is not installed).'}, status=500)
    except Exception:
        return JsonResponse({'status': 'error', 'message': 'The file is not a valid image or is corrupted.'})

    # Remove old picture if exists
    if profile.profile_picture:
        profile.profile_picture.delete(save=False)

    uploaded_file.seek(0)
    profile.profile_picture = uploaded_file
    profile.save()

    return JsonResponse({
        'status': 'ok',
        'message': 'Profile picture updated successfully.',
        'image_url': profile.profile_picture.url
    })

@login_required
def delete_profile_picture(request):
    """Hapus foto profil guru (AJAX)."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Method not allowed.'}, status=405)

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Profile missing.'}, status=403)

    if profile.profile_picture:
        profile.profile_picture.delete(save=False)
        profile.profile_picture = None
        profile.save()
        return JsonResponse({'status': 'ok', 'message': 'Profile picture removed.'})
    else:
        return JsonResponse({'status': 'error', 'message': 'No profile picture to delete.'})

@login_required
def log_activity(request):
    """Record an activity log entry for the current teacher."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method.'}, status=405)

    action = request.POST.get('action', '').strip()
    if not action:
        return JsonResponse({'status': 'error', 'message': 'Action required.'}, status=400)

    # Truncate to model max length
    if len(action) > 255:
        action = action[:255]

    ActivityLog.objects.create(teacher=request.user, action=action)

    # Cleanup: keep only the latest 100 entries per teacher
    keep_ids = list(
        ActivityLog.objects
        .filter(teacher=request.user)
        .order_by('-timestamp')
        .values_list('id', flat=True)[:100]
    )
    if keep_ids:
        ActivityLog.objects.filter(teacher=request.user).exclude(id__in=keep_ids).delete()

    return JsonResponse({'status': 'ok'})

@login_required
def sidebar_info(request):
    import os
    from datetime import datetime

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'Profile missing'}, status=403)

    # Semua kelas guru
    classes_to_check = Class.objects.filter(teacher=request.user, is_archived=False)

    # Hitung asesmen pending + grouping per kelas
    assessments_in_scope = Assessment.objects.filter(class_obj__in=classes_to_check)
    missing_count = 0
    first_missing_class_id = None
    pending_by_class = {}

    for ass in assessments_in_scope:
        total_students = Enrollment.objects.filter(
            class_obj=ass.class_obj,
            is_active=True
        ).count()
        scored_students = Score.objects.filter(assessment=ass).count()
        if scored_students < total_students:
            missing_count += 1
            if first_missing_class_id is None:
                first_missing_class_id = ass.class_obj_id
            cid = ass.class_obj_id
            if cid not in pending_by_class:
                pending_by_class[cid] = {
                    'name': ass.class_obj.name,
                    'count': 0
                }
            pending_by_class[cid]['count'] += 1

    # Class count & backup
    class_count = classes_to_check.count()
    title = dict(UserProfile.ROLE_CHOICES).get(profile.role, 'Teacher')

    from lms.services.backup_service import get_backup_status
    backup_status = get_backup_status()
    last_backup = backup_status['last_backup_str'] if backup_status['last_backup_str'] != 'Never' else None

        # Recent activity from database (latest 5)
    recent_logs = (
        ActivityLog.objects
        .filter(teacher=request.user)
        .order_by('-timestamp')[:5]
        .values('action', 'timestamp')
    )
    recent_activity = [
        {
            'action': log['action'],
            'time': timezone.localtime(log['timestamp']).strftime('%I:%M %p'),
        }
        for log in recent_logs
    ]

    return JsonResponse({
        'class_count': class_count,
        'title': title,
        'last_backup': last_backup,
        'backup_health': backup_status['health'],
        'backup_age_hours': backup_status['age_hours'],
        'backup_count': backup_status['count'],
        'missing_assessments_count': missing_count,
        'first_missing_class_id': first_missing_class_id,
        'pending_by_class': pending_by_class,
        'recent_activity': recent_activity,
    })
