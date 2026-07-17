from django.shortcuts import render, redirect
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

from .models import (
    Class, UserProfile, Enrollment, Student, AttendanceSession, AttendanceRecord,
    BehaviorEntry, BehaviorCategory, AssessmentType, Assessment, Score,
    StudentFeedback, Semester
)

# ---------- Helper Functions ----------
def custom_logout(request):
    logout(request)
    return redirect('login')


# ---------- Dashboard ----------
@login_required
def dashboard(request):
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return HttpResponse("You do not have a profile. Please contact the administrator.")

    if profile.role != 'teacher':
        return HttpResponse("Access restricted to teachers.")

    is_partial = request.GET.get('partial') == 'true'
    url_class_id = request.GET.get('class_id')

    selected_class_id = None
    if url_class_id and url_class_id.isdigit():
        selected_class_id = int(url_class_id)
    elif url_class_id == '':
        selected_class_id = None
    else:
        selected_class_id = None

    all_classes = Class.objects.filter(teacher=request.user)
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
    for cls in classes:
        enrollments = Enrollment.objects.filter(
            class_obj=cls, is_active=True
        ).select_related('student').order_by('student__name')

        student_ids = [e.student_id for e in enrollments]
        if not student_ids:
            class_data.append({'class': cls, 'students': []})
            continue

        # Behavior
        behavior_agg = BehaviorEntry.objects.filter(student_id__in=student_ids).values('student_id').annotate(
            total_positive=Coalesce(Sum('points', filter=Q(points__gt=0)), Value(0)),
            total_negative=Coalesce(Sum('points', filter=Q(points__lt=0)), Value(0))
        )
        behavior_dict = {
            item['student_id']: {
                'total_positive': item['total_positive'],
                'total_negative': abs(item['total_negative']),
                'net_points': item['total_positive'] + item['total_negative']
            }
            for item in behavior_agg
        }

        # Attendance
        attendance_agg = AttendanceRecord.objects.filter(
            student_id__in=student_ids,
            session__class_obj=cls
        ).values('student_id').annotate(
            total_sessions=Count('id'),
            present_count=Count('id', filter=Q(status__in=['present', 'late', 'excused', 'sick']))
        )
        attendance_dict = {}
        for item in attendance_agg:
            total = item['total_sessions']
            present = item['present_count']
            attendance_dict[item['student_id']] = {
                'total_sessions': total,
                'present_count': present,
                'percentage': (present / total * 100) if total > 0 else 0.0
            }

        # Academic: semua asesmen di kelas, tidak dikerjakan = 0
        assessments_in_class = Assessment.objects.filter(class_obj=cls)
        total_max_points = assessments_in_class.aggregate(total=Sum('max_points'))['total'] or 0

        scores_in_class = Score.objects.filter(
            student_id__in=student_ids,
            assessment__in=assessments_in_class
        ).values('student_id').annotate(total_earned=Sum('points_earned'))

        student_total_points = {item['student_id']: item['total_earned'] for item in scores_in_class}

        academic_dict = {}
        for sid in student_ids:
            earned = student_total_points.get(sid, 0)
            if total_max_points > 0:
                avg = (earned / total_max_points) * 100
            else:
                avg = 0.0
            academic_dict[sid] = avg

        students_data = []
        for enrollment in enrollments:
            student = enrollment.student

            if search_query and search_query.lower() not in student.name.lower():
                continue

            sid = student.id
            beh = behavior_dict.get(sid, {'total_positive': 0, 'total_negative': 0, 'net_points': 0})
            total_positive = beh['total_positive']
            total_negative = beh['total_negative']
            net_points = beh['net_points']
            has_behavior = (total_positive + total_negative) > 0

            att_data = attendance_dict.get(sid, {'total_sessions': 0, 'present_count': 0, 'percentage': 0.0})
            total_sessions = att_data['total_sessions']
            present_count = att_data['present_count']
            attendance_summary = f"{present_count}/{total_sessions}" if total_sessions > 0 else "0/0"
            attendance_percentage = att_data['percentage']
            has_attendance = total_sessions > 0

            academic_avg = academic_dict.get(sid, 0.0)
            has_academic = total_max_points > 0

            if has_academic or has_attendance or has_behavior:
                pos_cap = cls.positive_behavior_cap or 1
                neg_cap = cls.negative_behavior_cap or 1
                positive_component = min((total_positive / pos_cap) * 100, 100) if has_behavior else 0
                negative_component = max(100 - (abs(total_negative) / neg_cap) * 100, 0) if has_behavior else 100
                final_score = (
                    academic_avg * 0.6
                    + attendance_percentage * 0.15
                    + positive_component * 0.15
                    + negative_component * 0.1
                )
                final_score = min(round(final_score, 1), 100.0)
            else:
                final_score = None

            students_data.append({
                'student': student,
                'attendance_summary': attendance_summary,
                'attendance_percentage': round(attendance_percentage, 1),
                'total_positive': total_positive,
                'total_negative': total_negative,
                'net_points': net_points,
                'academic_avg': round(academic_avg, 1),
                'final_score': final_score,
            })

        class_data.append({'class': cls, 'students': students_data})

    # Highlight Siswa
    all_students_data = []
    for cls in all_classes:
        for item in class_data:
            if item['class'].id == cls.id:
                all_students_data.extend(item['students'])
                break

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
                    points = float(points_str.replace(',', '.'))  # dukung koma sebagai desimal
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
                    errors.append(f"Nilai untuk {student.name} tidak valid: '{points_str}'")
            # jika kosong, biarkan saja (tidak mengubah data yang sudah ada)

        # Susun pesan untuk pengguna
        if saved_count > 0:
            msg = f"{saved_count}  score(s) has been saved for '{assessment.name}'."
            if errors:
                msg += " Namun beberapa nilai gagal: " + "; ".join(errors[:3])  # maks 3 error
                if len(errors) > 3:
                    msg += f" (dan {len(errors)-3} lainnya)"
        else:
            if errors:
                msg = f"❌ Tidak ada skor yang tersimpan. Kesalahan: {'; '.join(errors[:3])}"
            else:
                msg = "Tidak ada skor diisi, tidak ada perubahan."

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

    points_str = request.POST.get('points')
    if not points_str:
        return JsonResponse({'status': 'error', 'message': 'Points not specified.'}, status=400)
    try:
        points = int(points_str)
    except ValueError:
        return JsonResponse({'status': 'error', 'message': 'Invalid points value.'}, status=400)

    category, _ = BehaviorCategory.objects.get_or_create(
        name='Quick Point', defaults={'default_points': points, 'is_positive': points > 0}
    )
    BehaviorEntry.objects.create(
        student=student, category=category, points=points,
        note=f"Quick {'positive' if points > 0 else 'negative'} point from dashboard",
        recorded_by=request.user
    )

    # Recalculate final score dengan metode baru (semua asesmen = 0 jika kosong)
    attendance_records = AttendanceRecord.objects.filter(student=student, session__class_obj=class_obj)
    total_sessions = attendance_records.count()
    present_count = attendance_records.filter(status__in=['present', 'late', 'excused', 'sick']).count()
    attendance_percentage = (present_count / total_sessions * 100) if total_sessions > 0 else 0.0

    behavior_entries = BehaviorEntry.objects.filter(student=student)
    total_positive = behavior_entries.filter(points__gt=0).aggregate(total=models.Sum('points'))['total'] or 0
    total_negative = abs(behavior_entries.filter(points__lt=0).aggregate(total=models.Sum('points'))['total'] or 0)
    net_points = total_positive - total_negative

    # Academic baru: total semua asesmen di kelas
    assessments_in_class = Assessment.objects.filter(class_obj=class_obj)
    total_max_points = assessments_in_class.aggregate(total=Sum('max_points'))['total'] or 0
    total_earned = Score.objects.filter(student=student, assessment__in=assessments_in_class).aggregate(
        total=Sum('points_earned'))['total'] or 0
    if total_max_points > 0:
        academic_avg = (total_earned / total_max_points) * 100
    else:
        academic_avg = 0.0
    has_academic = total_max_points > 0

    pos_cap = class_obj.positive_behavior_cap or 1
    neg_cap = class_obj.negative_behavior_cap or 1
    positive_component = min((total_positive / pos_cap) * 100, 100)
    negative_component = max(100 - (abs(total_negative) / neg_cap) * 100, 0)

    has_attendance = total_sessions > 0
    has_behavior = behavior_entries.exists()
    if has_academic or has_attendance or has_behavior:
        final_score = (
            academic_avg * 0.6 + attendance_percentage * 0.15
            + positive_component * 0.15 + negative_component * 0.1
        )
        final_score = min(round(final_score, 1), 100.0)
    else:
        final_score = None

    new_summary = (
        '<div class="d-flex align-items-center justify-content-center">'
        '<span class="text-nowrap" style="width: 85px; display: inline-block; text-align: left;">'
        f'<span class="text-success fw-semibold">+{total_positive}</span> '
        '<span class="text-muted">/</span> '
        f'<span class="text-danger fw-semibold">-{total_negative}</span>'
        '</span>'
        '<span class="border-start ps-2 ms-1 text-nowrap">'
        f'<strong>Net: {net_points}</strong>'
        '</span>'
        '</div>'
    )

    return JsonResponse({
        'status': 'ok', 'message': f'Added {points} points to {student.name}.',
        'new_summary': new_summary, 'new_final_score': final_score,
        'total_positive': total_positive, 'total_negative': total_negative, 'net_points': net_points,
    })


# ---------- Reset Points ----------
@login_required
def reset_student_points(request, student_id, class_id):
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

    BehaviorEntry.objects.filter(student=student).delete()

    attendance_records = AttendanceRecord.objects.filter(student=student, session__class_obj=class_obj)
    total_sessions = attendance_records.count()
    present_count = attendance_records.filter(status__in=['present', 'late', 'excused', 'sick']).count()
    attendance_percentage = (present_count / total_sessions * 100) if total_sessions > 0 else 0.0

    # Academic baru
    assessments_in_class = Assessment.objects.filter(class_obj=class_obj)
    total_max_points = assessments_in_class.aggregate(total=Sum('max_points'))['total'] or 0
    total_earned = Score.objects.filter(student=student, assessment__in=assessments_in_class).aggregate(
        total=Sum('points_earned'))['total'] or 0
    if total_max_points > 0:
        academic_avg = (total_earned / total_max_points) * 100
    else:
        academic_avg = 0.0
    has_academic = total_max_points > 0

    pos_cap = class_obj.positive_behavior_cap or 1
    neg_cap = class_obj.negative_behavior_cap or 1
    positive_component = 0
    negative_component = 100

    has_attendance = total_sessions > 0
    if has_academic or has_attendance:
        final_score = (
            academic_avg * 0.6 + attendance_percentage * 0.15
            + positive_component * 0.15 + negative_component * 0.1
        )
        final_score = min(round(final_score, 1), 100.0)
    else:
        final_score = None

    new_summary = (
        '<div class="d-flex align-items-center justify-content-center">'
        '<span class="text-nowrap" style="width: 85px; display: inline-block; text-align: left;">'
        '<span class="text-success fw-semibold">+0</span> '
        '<span class="text-muted">/</span> '
        '<span class="text-danger fw-semibold">-0</span>'
        '</span>'
        '<span class="border-start ps-2 ms-1 text-nowrap">'
        '<strong>Net: 0</strong>'
        '</span>'
        '</div>'
    )

    return JsonResponse({
        'status': 'ok', 'message': f'Behavior points for {student.name} have been reset.',
        'new_summary': new_summary, 'new_final_score': final_score,
    })


@login_required
def reset_class_points(request, class_id):
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

    students = Enrollment.objects.filter(class_obj=class_obj, is_active=True).values_list('student', flat=True)
    BehaviorEntry.objects.filter(student__in=students).delete()

    return JsonResponse({'status': 'ok', 'message': f"Behavior points for all students in {class_obj.name} have been reset."})


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

    all_classes = Class.objects.filter(teacher=request.user)

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

    chart_class_names = []
    chart_class_avg_scores = []
    chart_components = {'academic': [], 'attendance': [], 'positive': [], 'negative': []}

    for cls in all_classes:
        enrollments = Enrollment.objects.filter(class_obj=cls, is_active=True).select_related('student')
        student_ids = [e.student_id for e in enrollments]
        if not student_ids:
            chart_class_names.append(cls.name)
            chart_class_avg_scores.append(0)
            for k in chart_components:
                chart_components[k].append(0)
            continue

        # Behavior
        beh_agg = BehaviorEntry.objects.filter(student_id__in=student_ids).values('student_id').annotate(
            total_positive=Coalesce(Sum('points', filter=Q(points__gt=0)), Value(0)),
            total_negative=Coalesce(Sum('points', filter=Q(points__lt=0)), Value(0))
        )
        beh_dict = {}
        for item in beh_agg:
            beh_dict[item['student_id']] = {'pos': item['total_positive'], 'neg': abs(item['total_negative'])}

        # Attendance
        att_agg = AttendanceRecord.objects.filter(
            student_id__in=student_ids, session__class_obj=cls
        ).values('student_id').annotate(
            total_sessions=Count('id'),
            present_count=Count('id', filter=Q(status__in=['present', 'late', 'excused', 'sick']))
        )
        att_dict = {}
        for item in att_agg:
            total = item['total_sessions']
            present = item['present_count']
            att_dict[item['student_id']] = (present / total * 100) if total > 0 else 0.0

        # Academic baru (semua asesmen, tidak dikerjakan = 0)
        assessments_in_cls = Assessment.objects.filter(class_obj=cls)
        total_max = assessments_in_cls.aggregate(total=Sum('max_points'))['total'] or 0
        scores_for_cls = Score.objects.filter(
            student_id__in=student_ids,
            assessment__in=assessments_in_cls
        ).values('student_id').annotate(earned=Sum('points_earned'))

        acad_dict = {}
        for item in scores_for_cls:
            if total_max > 0:
                acad_dict[item['student_id']] = (item['earned'] / total_max) * 100
            else:
                acad_dict[item['student_id']] = 0.0
        for sid in student_ids:
            if sid not in acad_dict:
                acad_dict[sid] = 0.0

        # Komponen nilai akhir
        total_final = total_academic = total_attendance = total_positive_comp = total_negative_comp = count = 0
        for enrollment in enrollments:
            sid = enrollment.student_id
            beh = beh_dict.get(sid, {'pos': 0, 'neg': 0})
            total_pos, total_neg = beh['pos'], beh['neg']
            att_pct = att_dict.get(sid, 0.0)
            acad_avg = acad_dict.get(sid, 0.0)

            pos_cap = cls.positive_behavior_cap or 1
            neg_cap = cls.negative_behavior_cap or 1
            pos_comp = min((total_pos / pos_cap) * 100, 100)
            neg_comp = max(100 - (abs(total_neg) / neg_cap) * 100, 0)

            final = acad_avg * 0.6 + att_pct * 0.15 + pos_comp * 0.15 + neg_comp * 0.1
            final = min(round(final, 1), 100.0)

            total_final += final
            total_academic += acad_avg
            total_attendance += att_pct
            total_positive_comp += pos_comp
            total_negative_comp += neg_comp
            count += 1

        if count > 0:
            chart_class_names.append(cls.name)
            chart_class_avg_scores.append(round(total_final / count, 1))
            chart_components['academic'].append(round(total_academic / count, 1))
            chart_components['attendance'].append(round(total_attendance / count, 1))
            chart_components['positive'].append(round(total_positive_comp / count, 1))
            chart_components['negative'].append(round(total_negative_comp / count, 1))
        else:
            chart_class_names.append(cls.name)
            chart_class_avg_scores.append(0)
            for k in chart_components:
                chart_components[k].append(0)

    # Histogram (dengan metode baru)
    score_ranges = ['<60', '60-70', '70-80', '80-90', '≥90']
    range_counts = [0, 0, 0, 0, 0]
    if selected_class_id:
        try:
            cls = Class.objects.get(id=selected_class_id, teacher=request.user)
            enrollments = Enrollment.objects.filter(class_obj=cls, is_active=True).select_related('student')
            student_ids = [e.student_id for e in enrollments]
            if student_ids:
                # Behavior
                beh_agg = BehaviorEntry.objects.filter(student_id__in=student_ids).values('student_id').annotate(
                    total_positive=Coalesce(Sum('points', filter=Q(points__gt=0)), Value(0)),
                    total_negative=Coalesce(Sum('points', filter=Q(points__lt=0)), Value(0))
                )
                beh_dict = {item['student_id']: (item['total_positive'], abs(item['total_negative'])) for item in beh_agg}

                # Attendance
                att_agg = AttendanceRecord.objects.filter(
                    student_id__in=student_ids, session__class_obj=cls
                ).values('student_id').annotate(
                    total_sessions=Count('id'),
                    present_count=Count('id', filter=Q(status__in=['present', 'late', 'excused', 'sick']))
                )
                att_dict = {}
                for item in att_agg:
                    total = item['total_sessions']
                    present = item['present_count']
                    att_dict[item['student_id']] = (present / total * 100) if total > 0 else 0.0

                # Academic baru
                assessments_in_cls = Assessment.objects.filter(class_obj=cls)
                total_max = assessments_in_cls.aggregate(total=Sum('max_points'))['total'] or 0
                scores_for_cls = Score.objects.filter(
                    student_id__in=student_ids,
                    assessment__in=assessments_in_cls
                ).values('student_id').annotate(earned=Sum('points_earned'))
                acad_dict = {}
                for item in scores_for_cls:
                    if total_max > 0:
                        acad_dict[item['student_id']] = (item['earned'] / total_max) * 100
                    else:
                        acad_dict[item['student_id']] = 0.0
                for sid in student_ids:
                    if sid not in acad_dict:
                        acad_dict[sid] = 0.0

                for enrollment in enrollments:
                    sid = enrollment.student_id
                    pos, neg = beh_dict.get(sid, (0, 0))
                    att_pct = att_dict.get(sid, 0.0)
                    acad_avg = acad_dict.get(sid, 0.0)

                    pos_cap = cls.positive_behavior_cap or 1
                    neg_cap = cls.negative_behavior_cap or 1
                    pos_comp = min((pos / pos_cap) * 100, 100)
                    neg_comp = max(100 - (abs(neg) / neg_cap) * 100, 0)

                    final = acad_avg * 0.6 + att_pct * 0.15 + pos_comp * 0.15 + neg_comp * 0.1
                    final = min(round(final, 1), 100.0)

                    if final < 60: range_counts[0] += 1
                    elif final < 70: range_counts[1] += 1
                    elif final < 80: range_counts[2] += 1
                    elif final < 90: range_counts[3] += 1
                    else: range_counts[4] += 1
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


# ---------- AI Feedback ----------
def generate_ai_feedback_rule_based(student, class_obj, academic_avg, attendance_summary,
                                    total_positive, total_negative, net_points, final_score, assessment_details):
    feedback = f"Laporan Perkembangan {student.name} - {class_obj.name}\n\n"
    feedback += f"Rata-rata akademik: {academic_avg:.1f}. Kehadiran: {attendance_summary}. Skor akhir: {final_score}.\n\n"
    feedback += "Detail nilai:\n"
    for d in assessment_details:
        feedback += f"- {d['name']} ({d['date']}): {d['percentage']}% ({d['score']}/{d['max_points']})"
        if d['notes']: feedback += f" — Catatan: {d['notes']}"
        feedback += "\n"
    feedback += f"\nPerilaku: positif {total_positive}, negatif {total_negative}, net {net_points}.\n\n"

    if academic_avg >= 85: feedback += "Prestasi akademik sangat baik. "
    elif academic_avg >= 70: feedback += "Nilai akademik cukup baik. "
    else: feedback += "Nilai akademik perlu ditingkatkan. "

    if attendance_summary != "0/0": feedback += "Kehadiran tercatat. "
    else: feedback += "Kehadiran belum tercatat. "

    if net_points >= 5: feedback += "Perilaku sangat positif."
    elif net_points >= 0: feedback += "Perilaku cukup baik."
    else: feedback += "Perilaku perlu perhatian."

    feedback += "\n\nSaran: Diskusikan dengan guru untuk rencana perbaikan."
    return feedback

def generate_ai_feedback(student, class_obj):
    scores = Score.objects.filter(student=student, assessment__class_obj=class_obj).select_related('assessment')
    assessment_details = []
    for sc in scores:
        ass = sc.assessment
        pct = (sc.points_earned / ass.max_points) * 100
        assessment_details.append({
            'name': ass.name,
            'date': ass.date.strftime('%d %b %Y'),
            'score': sc.points_earned,
            'max_points': ass.max_points,
            'percentage': round(pct, 1),
            'notes': sc.notes or ''
        })

    all_assessments = Assessment.objects.filter(class_obj=class_obj)
    assessed_ids = set(scores.values_list('assessment_id', flat=True))
    missing_assessments = [a for a in all_assessments if a.id not in assessed_ids]
    missing_count = len(missing_assessments)

    # Hitung rata-rata berdasarkan semua asesmen (tidak dikerjakan = 0)
    total_max_all = all_assessments.aggregate(total=Sum('max_points'))['total'] or 0
    total_earned_all = scores.aggregate(total=Sum('points_earned'))['total'] or 0
    if total_max_all > 0:
        academic_avg = (total_earned_all / total_max_all) * 100
    else:
        academic_avg = 0.0

    if total_max_all > 0:
        academic_status = f"Rata‑rata nilai Ananda {student.name} dari seluruh {all_assessments.count()} asesmen di kelas adalah {academic_avg:.1f}."
        if missing_count > 0:
            academic_status += f" Namun, masih ada {missing_count} asesmen yang belum memiliki nilai."
    else:
        academic_status = "Belum ada asesmen di kelas ini."

    attendance_records = AttendanceRecord.objects.filter(student=student, session__class_obj=class_obj)
    total_sessions = attendance_records.count()
    present_count = attendance_records.filter(status__in=['present', 'late', 'excused', 'sick']).count()
    attendance_summary = f"{present_count}/{total_sessions}" if total_sessions > 0 else "0/0"
    attendance_percentage = (present_count / total_sessions * 100) if total_sessions > 0 else 0.0

    behavior_entries = BehaviorEntry.objects.filter(student=student)
    total_positive = behavior_entries.filter(points__gt=0).aggregate(total=models.Sum('points'))['total'] or 0
    total_negative = abs(behavior_entries.filter(points__lt=0).aggregate(total=models.Sum('points'))['total'] or 0)
    net_points = total_positive - total_negative

    pos_cap = class_obj.positive_behavior_cap or 1
    neg_cap = class_obj.negative_behavior_cap or 1
    positive_component = min((total_positive / pos_cap) * 100, 100) if total_positive > 0 else 0
    negative_component = max(100 - (abs(total_negative) / neg_cap) * 100, 0) if total_negative > 0 else 100

    if academic_avg is not None:
        academic_part = academic_avg * 0.6
    else:
        academic_part = 0

    final_score = (
        academic_part + attendance_percentage * 0.15 + positive_component * 0.15 + negative_component * 0.1
    )
    final_score = min(round(final_score, 1), 100.0) if academic_avg is not None else None

    teacher_name = class_obj.teacher.get_full_name() or class_obj.teacher.username
    bulan_sekarang = datetime.now().strftime('%B %Y')

    prompt = f"""Anda adalah {teacher_name}, seorang guru yang hangat dan komunikatif. Tulislah SURAT PRIBADI untuk orang tua/wali dari Ananda {student.name} di kelas {class_obj.name}. Gunakan Bahasa Indonesia yang mengalir, santun, dan personal. Surat boleh terdiri dari beberapa paragraf pendek. (Saat ini adalah {bulan_sekarang}, Anda bisa merujuk pada periode akademik yang sedang berlangsung).

**Yang harus ada dalam surat (tidak harus berurutan):**
- Salam pembuka "Assalamualaikum Warahmatullahi Wabarakatuh".
- Apresiasi terhadap pencapaian atau karakter positif Ananda.
- Gambaran umum tentang perkembangan akademik: {academic_status}
- Informasi kehadiran dan perilaku: Kehadiran {attendance_summary} ({attendance_percentage:.1f}%), Poin positif {total_positive}, Poin negatif {total_negative}. **Jika poin positif tinggi (>=10), beri pujian bahwa Ananda aktif dan disiplin. Jika poin negatif rendah (0-2), sampaikan sikapnya sudah baik. Jika poin negatif tinggi (>5), sampaikan dengan pengertian dan tawarkan strategi perbaikan.**
- Skor akhir sebagai ringkasan: {"Skor akhir: " + str(final_score) if final_score is not None else "Skor akhir belum dapat dihitung."}
- Motivasi dan harapan, termasuk solusi untuk siswa asrama: pentingnya komunikasi orang tua lewat telepon/video call, koordinasi dengan wali asrama, dll.
- Kalimat penutup yang sopan, lalu "Hormat kami, {teacher_name}" (JANGAN tulis "Wali Kelas").

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
- Jangan mengulang data mentah, tapi ceritakanlah dengan bahasa yang enak dibaca.
- Jika ada area yang perlu ditingkatkan, sampaikan dengan optimis dan penuh pengertian.
- Bebas menggunakan variasi kalimat, sinonim, dan gaya bahasa asalkan tetap sopan.
- Akhiri surat dengan nada positif yang menyemangati.

**Panjang surat:** sekitar 180–250 kata.
"""

    # ===== PERUBAHAN: Import ollama di dalam fungsi dengan fallback =====
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
                student, class_obj, academic_avg if academic_avg else 0, attendance_summary,
                total_positive, total_negative, net_points, final_score if final_score else 0,
                assessment_details
            )
        return feedback
    except ImportError:
        # ollama tidak terinstal, langsung gunakan fallback rule-based
        return generate_ai_feedback_rule_based(
            student, class_obj, academic_avg if academic_avg else 0, attendance_summary,
            total_positive, total_negative, net_points, final_score if final_score else 0,
            assessment_details
        )
    except Exception as e:
        # Error lain saat memanggil ollama (misal server tidak berjalan), fallback
        print(f"Ollama error: {e}")  # Bisa diganti dengan logging yang tepat
        return generate_ai_feedback_rule_based(
            student, class_obj, academic_avg if academic_avg else 0, attendance_summary,
            total_positive, total_negative, net_points, final_score if final_score else 0,
            assessment_details
        )

@login_required
def student_feedback(request, student_id, class_id):
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

    # Data untuk ditampilkan (menggunakan perhitungan baru)
    all_assessments = Assessment.objects.filter(class_obj=class_obj)
    total_max_all = all_assessments.aggregate(total=Sum('max_points'))['total'] or 0
    total_earned_all = Score.objects.filter(student=student, assessment__in=all_assessments).aggregate(total=Sum('points_earned'))['total'] or 0
    if total_max_all > 0:
        academic_avg = (total_earned_all / total_max_all) * 100
    else:
        academic_avg = 80.0  # fallback

    attendance_records = AttendanceRecord.objects.filter(student=student, session__class_obj=class_obj)
    total_sessions = attendance_records.count()
    present_count = attendance_records.filter(status__in=['present', 'late', 'excused', 'sick']).count()
    attendance_summary = f"{present_count}/{total_sessions}" if total_sessions > 0 else "0/0"
    attendance_percentage = (present_count / total_sessions * 100) if total_sessions > 0 else 0.0

    behavior_entries = BehaviorEntry.objects.filter(student=student)
    total_positive = behavior_entries.filter(points__gt=0).aggregate(total=models.Sum('points'))['total'] or 0
    total_negative = abs(behavior_entries.filter(points__lt=0).aggregate(total=models.Sum('points'))['total'] or 0)
    net_points = total_positive - total_negative

    pos_cap = class_obj.positive_behavior_cap or 1
    neg_cap = class_obj.negative_behavior_cap or 1
    positive_component = min((total_positive / pos_cap) * 100, 100)
    negative_component = max(100 - (abs(total_negative) / neg_cap) * 100, 0)
    final_score = (
        academic_avg * 0.6 + attendance_percentage * 0.15
        + positive_component * 0.15 + negative_component * 0.1
    )
    final_score = min(round(final_score, 1), 100.0)

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
                else:
                    messages.success(request, "Feedback saved.")
        elif action == 'generate_ai':
            new_text = generate_ai_feedback(student, class_obj)
            feedback_obj.feedback_text = new_text
            feedback_obj.generated_by_ai = True
            feedback_obj.save()
            messages.success(request, "AI feedback generated.")
        return redirect('student_feedback', student_id=student_id, class_id=class_id)

    # assessment_details untuk JS
    scores = Score.objects.filter(student=student, assessment__class_obj=class_obj).select_related('assessment')
    assessment_details = []
    for sc in scores:
        ass = sc.assessment
        pct = (sc.points_earned / ass.max_points) * 100
        assessment_details.append({
            'name': ass.name, 'date': ass.date.strftime('%d %b %Y'),
            'score': sc.points_earned, 'max_points': ass.max_points,
            'percentage': round(pct, 1), 'notes': sc.notes
        })
    
    # Hitung asesmen yang belum dinilai untuk ditampilkan di UI
    all_assessments = Assessment.objects.filter(class_obj=class_obj)
    assessed_ids = set(Score.objects.filter(student=student, assessment__in=all_assessments)
                   .values_list('assessment_id', flat=True))
    missing_assessments = [a for a in all_assessments if a.id not in assessed_ids]

    context = {
        'student': student,
        'class_obj': class_obj,
        'feedback': feedback_obj,
        'academic_avg': round(academic_avg, 1),
        'attendance_percentage': round(attendance_percentage, 1),
        'total_positive': total_positive,
        'total_negative': total_negative,
        'net_points': net_points,
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
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.graphics.shapes import Drawing, Line
import io, os, re, zipfile
from io import BytesIO

def _generate_report_pdf_buffer(student, class_obj):
    # Gunakan metode baru untuk academic_avg
    all_assessments = Assessment.objects.filter(class_obj=class_obj)
    total_max = all_assessments.aggregate(total=Sum('max_points'))['total'] or 0
    total_earned = Score.objects.filter(student=student, assessment__in=all_assessments).aggregate(total=Sum('points_earned'))['total'] or 0
    if total_max > 0:
        academic_avg = (total_earned / total_max) * 100
    else:
        academic_avg = 80.0

    scores = Score.objects.filter(student=student, assessment__class_obj=class_obj).select_related('assessment')
    assessment_details = []
    for sc in scores:
        ass = sc.assessment
        pct = (sc.points_earned / ass.max_points) * 100
        assessment_details.append({
            'name': ass.name, 'date': ass.date.strftime('%d %b %Y'),
            'score': sc.points_earned, 'max': ass.max_points,
            'percentage': round(pct, 1), 'notes': sc.notes
        })

    attendance_records = AttendanceRecord.objects.filter(student=student, session__class_obj=class_obj)
    total_sessions = attendance_records.count()
    present_count = attendance_records.filter(status__in=['present', 'late', 'excused', 'sick']).count()
    attendance_summary = f"{present_count}/{total_sessions}" if total_sessions > 0 else "0/0"
    attendance_percentage = (present_count / total_sessions * 100) if total_sessions > 0 else 0.0

    behavior_entries = BehaviorEntry.objects.filter(student=student)
    total_positive = behavior_entries.filter(points__gt=0).aggregate(total=models.Sum('points'))['total'] or 0
    total_negative = abs(behavior_entries.filter(points__lt=0).aggregate(total=models.Sum('points'))['total'] or 0)
    net_points = total_positive - total_negative

    pos_cap = class_obj.positive_behavior_cap or 1
    neg_cap = class_obj.negative_behavior_cap or 1
    positive_component = min((total_positive / pos_cap) * 100, 100) if total_positive > 0 else 0
    negative_component = max(100 - (abs(total_negative) / neg_cap) * 100, 0) if total_negative > 0 else 100
    final_score = (
        academic_avg * 0.6 + attendance_percentage * 0.15
        + positive_component * 0.15 + negative_component * 0.1
    )
    final_score = min(round(final_score, 1), 100.0)

    feedback_obj = StudentFeedback.objects.filter(
        student=student, class_obj=class_obj, semester=class_obj.semester
    ).first()
    feedback_text = feedback_obj.feedback_text if feedback_obj else "Belum ada feedback dari guru."

    semester_name = class_obj.semester.name
    if "even" in semester_name.lower() or "genap" in semester_name.lower():
        semester_id = "Semester Genap"
    elif "odd" in semester_name.lower() or "ganjil" in semester_name.lower():
        semester_id = "Semester Ganjil"
    else:
        semester_id = semester_name

    def fmt_num(n):
        return str(int(n)) if isinstance(n, float) and n.is_integer() else f"{n:.1f}"

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1.8*cm, leftMargin=1.8*cm,
                            topMargin=1.8*cm, bottomMargin=1.5*cm)
    story = []
    styles = getSampleStyleSheet()

    PRIMARY_COLOR = colors.HexColor('#1e3a5f')
    LIGHT_BG = colors.HexColor('#f4f6f9')
    GREY_TEXT = colors.HexColor('#555555')
    base_normal = styles['Normal']

    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontName='Helvetica-Bold',
                                 fontSize=20, textColor=PRIMARY_COLOR, alignment=TA_CENTER, spaceAfter=6)
    subtitle_style = ParagraphStyle('Subtitle', parent=base_normal, fontName='Helvetica',
                                    fontSize=11, textColor=GREY_TEXT, alignment=TA_CENTER, spaceAfter=20)
    heading_style = ParagraphStyle('Heading', parent=styles['Heading2'], fontName='Helvetica-Bold',
                                   fontSize=13, textColor=PRIMARY_COLOR, spaceBefore=18, spaceAfter=10,
                                   keepWithNext=True)
    normal_style = ParagraphStyle('Normal', parent=base_normal, fontName='Helvetica', fontSize=10,
                                  leading=14, textColor=colors.black, spaceAfter=8,
                                  allowWidows=0, allowOrphans=0)
    info_label_style = ParagraphStyle('InfoLabel', parent=base_normal, fontName='Helvetica-Bold',
                                      fontSize=10, textColor=PRIMARY_COLOR, alignment=TA_CENTER, spaceAfter=2)
    info_value_style = ParagraphStyle('InfoValue', parent=base_normal, fontName='Helvetica',
                                      fontSize=11, textColor=colors.black, alignment=TA_CENTER, spaceAfter=6)
    box_label_style = ParagraphStyle('BoxLabel', parent=base_normal, fontName='Helvetica', fontSize=9,
                                     textColor=GREY_TEXT, alignment=TA_CENTER, spaceAfter=2)
    box_value_style = ParagraphStyle('BoxValue', parent=base_normal, fontName='Helvetica-Bold',
                                     fontSize=14, textColor=PRIMARY_COLOR, alignment=TA_CENTER, spaceAfter=4)
    right_header_style = ParagraphStyle('RightHeader', parent=base_normal, fontName='Helvetica',
                                        fontSize=9, textColor=GREY_TEXT, alignment=TA_RIGHT,
                                        spaceBefore=-20, spaceAfter=4)
    bullet_style = ParagraphStyle('Bullet', parent=normal_style, leftIndent=20,
                                  fontSize=10, leading=14, spaceAfter=4)
    footer_style = ParagraphStyle('Footer', parent=base_normal, fontName='Helvetica',
                                  fontSize=8, textColor=GREY_TEXT, alignment=TA_CENTER,
                                  spaceAfter=4, allowWidows=0, allowOrphans=0)

    story.append(Paragraph(f"{class_obj.name} — {semester_id}", right_header_style))
    story.append(Spacer(1, 0.05*inch))
    logo_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'logo.png')
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=1.0*inch, height=1.0*inch)
        logo.hAlign = 'CENTER'
        story.append(logo)
        story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph("LAPORAN PERKEMBANGAN SISWA", title_style))
    story.append(Paragraph("SMP Al-Izzah Leadership School Batu", subtitle_style))
    line = Drawing(460, 1)
    line.add(Line(0, 0, 460, 0))
    story.append(line)
    story.append(Spacer(1, 0.25*inch))

    info_rows = [
        [Paragraph("<b>Nama Siswa</b>", info_label_style),
         Paragraph("<b>Kelas</b>", info_label_style),
         Paragraph("<b>Pengajar</b>", info_label_style)],
        [Paragraph(student.name, info_value_style),
         Paragraph(class_obj.name, info_value_style),
         Paragraph(class_obj.teacher.get_full_name() or class_obj.teacher.username, info_value_style)]
    ]
    info_table = Table(info_rows, colWidths=[doc.width/3.0]*3)
    info_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,0), 4), ('BOTTOMPADDING', (0,0), (-1,0), 2),
        ('TOPPADDING', (0,1), (-1,1), 2), ('BOTTOMPADDING', (0,1), (-1,1), 6),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.06*inch))

    story.append(Paragraph("Ringkasan Capaian", heading_style))
    metrics = [
        ("Rata-rata Akademik", fmt_num(academic_avg)),
        ("Kehadiran", attendance_summary),
        ("Poin Positif", f"+{total_positive}"),
        ("Poin Negatif", f"-{total_negative}"),
        ("Net Poin", str(net_points)),
        ("Final Score", fmt_num(final_score))
    ]
    rows = []
    for i in range(0, len(metrics), 3):
        row_cells = []
        for j in range(3):
            if i + j < len(metrics):
                label, value = metrics[i + j]
                cell = Table([[Paragraph(label, box_label_style)], [Paragraph(value, box_value_style)]],
                             colWidths=[doc.width/3.0 - 8])
                cell.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), LIGHT_BG),
                    ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#d0d0d0')),
                    ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ('TOPPADDING', (0,0), (-1,-1), 10), ('BOTTOMPADDING', (0,0), (-1,-1), 10),
                ]))
                row_cells.append(cell)
            else:
                row_cells.append(Paragraph("", normal_style))
        rows.append(row_cells)
    summary_table = Table(rows, colWidths=[doc.width/3.0]*3)
    summary_table.setStyle(TableStyle([
        ('LEFTPADDING', (0,0), (-1,-1), 4), ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 2), ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.06*inch))

    if assessment_details:
        story.append(Paragraph("Rincian Nilai Tugas / Ujian", heading_style))
        ass_data = [["No.", "Topik", "Tanggal", "Nilai", "%"]]
        for i, d in enumerate(assessment_details, 1):
            ass_data.append([
                str(i), Paragraph(d['name'], normal_style), d['date'],
                f"{fmt_num(d['score'])}/{fmt_num(d['max'])}", f"{fmt_num(d['percentage'])}%"
            ])
        ass_table = Table(ass_data, colWidths=[30, 200, 80, 60, 50], repeatRows=1)
        ass_table.setStyle(TableStyle([
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica'), ('FONTSIZE', (0,0), (-1,-1), 10),
            ('BACKGROUND', (0,0), (-1,0), PRIMARY_COLOR), ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cccccc')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#fafafa')]),
            ('TOPPADDING', (0,0), (-1,-1), 8), ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ]))
        story.append(ass_table)
        story.append(Spacer(1, 0.12*inch))
        story.append(Paragraph("* % = Persentase capaian terhadap nilai maksimal.", normal_style))
        story.append(Spacer(1, 0.25*inch))

    story.append(Paragraph("Catatan / Feedback Guru", heading_style))
    clean_feedback = re.sub(r'\*\*(.*?)\*\*', r'\1', feedback_text)
    clean_feedback = re.sub(r'\*(.*?)\*', r'\1', clean_feedback)
    clean_feedback = clean_feedback.replace('#', '')
    feedback_paragraphs = [p.strip() for p in clean_feedback.split('\n') if p.strip()]
    if not feedback_paragraphs:
        feedback_paragraphs = ["Belum ada feedback dari guru."]
    feedback_content = []
    for i, para in enumerate(feedback_paragraphs):
        feedback_content.append(Paragraph(para, normal_style))
        if i < len(feedback_paragraphs) - 1:
            feedback_content.append(Spacer(1, 0.06*inch))
    feedback_table = Table([[feedback_content]], colWidths=[doc.width])
    feedback_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), LIGHT_BG), ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#c0c0c0')),
        ('TOPPADDING', (0,0), (-1,-1), 12), ('BOTTOMPADDING', (0,0), (-1,-1), 12),
        ('LEFTPADDING', (0,0), (-1,-1), 15), ('RIGHTPADDING', (0,0), (-1,-1), 15),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(feedback_table)
    story.append(Spacer(1, 0.06*inch))

    story.append(Paragraph("Informasi Sistem Poin Perilaku", heading_style))
    behavior_content = []
    behavior_content.append(Paragraph("<b>✅ Perilaku Positif (Dihargai)</b>", normal_style))
    positive_items = [
        "Partisipasi Aktif: Menjawab pertanyaan, mengajukan pertanyaan kritis.",
        "Kepedulian Sosial: Membantu teman yang kesulitan memahami pelajaran.",
        "Tanggung Jawab Pribadi: Mengumpulkan tugas tepat waktu, membawa perlengkapan lengkap.",
        "Inisiatif Lingkungan: Merapikan kelas, membersihkan papan tulis tanpa disuruh.",
        "Peningkatan Akademik: Nilai ulangan menunjukkan kemajuan signifikan.",
        "Sportivitas: Menghargai pendapat atau penampilan teman."
    ]
    for item in positive_items:
        behavior_content.append(Paragraph(f"• {item}", bullet_style))
    behavior_content.append(Spacer(1, 0.06*inch))
    behavior_content.append(Paragraph("<b>❌ Perilaku Negatif (Dikurangi)</b>", normal_style))
    negative_items = [
        "Mengganggu KBM: Mengobrol saat guru menjelaskan, bercanda berlebihan.",
        "Ketidaksiapan Belajar: Tidak membawa buku paket atau alat tulis.",
        "Penyalahgunaan Etika: Keluar-masuk kelas tanpa izin.",
        "Pelanggaran Integritas: Mencontek, berbohong, membuat alasan palsu.",
        "Sikap Tidak Menghargai: Mengejek jawaban teman, membantah dengan nada tinggi."
    ]
    for item in negative_items:
        behavior_content.append(Paragraph(f"• {item}", bullet_style))
    behavior_content.append(Spacer(1, 0.06*inch))
    behavior_content.append(Paragraph(
        "<i>Catatan Inti: Sistem ini berfungsi untuk mencatat karakter, bukan menghakimi. "
        "Siswa tetap diberi kesempatan memperbaiki diri melalui tindakan positif pengganti.</i>", normal_style))
    behavior_table = Table([[behavior_content]], colWidths=[doc.width])
    behavior_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.white), ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#a0a0a0')),
        ('TOPPADDING', (0,0), (-1,-1), 12), ('BOTTOMPADDING', (0,0), (-1,-1), 12),
        ('LEFTPADDING', (0,0), (-1,-1), 15), ('RIGHTPADDING', (0,0), (-1,-1), 15),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(behavior_table)
    story.append(Spacer(1, 0.06*inch))

    signature_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'sig.png')
    full_name = class_obj.teacher.get_full_name() or class_obj.teacher.username
    teacher_name = full_name.split(',')[0].strip()
    center_style = ParagraphStyle('CenterStyle', parent=normal_style, alignment=TA_CENTER, fontSize=11, leading=16)
    right_content = []
    right_content.append(Paragraph("<b>Pengajar</b>", center_style))
    right_content.append(Spacer(1, 0.15*inch))
    if os.path.exists(signature_path):
        signature_img = Image(signature_path, width=1.5*inch, height=0.6*inch)
        signature_img.hAlign = 'CENTER'
        right_content.append(signature_img)
        right_content.append(Spacer(1, 0.1*inch))
    else:
        right_content.append(Paragraph("<i>(tanda tangan digital)</i>", center_style))
        right_content.append(Spacer(1, 0.1*inch))
    right_content.append(Paragraph(f"<b>{teacher_name}</b>", center_style))
    signature_data = [[Paragraph("", normal_style), right_content]]
    signature_table = Table(signature_data, colWidths=[doc.width*0.55, doc.width*0.45])
    signature_table.setStyle(TableStyle([
        ('ALIGN', (1,0), (1,0), 'CENTER'), ('VALIGN', (1,0), (1,0), 'TOP'),
        ('LEFTPADDING', (1,0), (1,0), 0), ('RIGHTPADDING', (1,0), (1,0), 0),
        ('TOPPADDING', (1,0), (1,0), 20),
    ]))
    story.append(signature_table)
    story.append(Spacer(1, 0.2*inch))

    story.append(Paragraph(f"Dicetak pada: {timezone.now().strftime('%d %B %Y, %H:%M')}", footer_style))
    story.append(Paragraph("Laporan ini dihasilkan secara otomatis dari Classroom LMS by Andhivie", footer_style))

    doc.build(story)
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
    student_ids = [s.id for s in students]

    data = []
    if student_ids:
        # Behavior
        beh_agg = BehaviorEntry.objects.filter(student_id__in=student_ids).values('student_id').annotate(
            total_positive=Coalesce(Sum('points', filter=Q(points__gt=0)), Value(0)),
            total_negative=Coalesce(Sum('points', filter=Q(points__lt=0)), Value(0))
        )
        beh_dict = {}
        for item in beh_agg:
            beh_dict[item['student_id']] = {'pos': item['total_positive'], 'neg': abs(item['total_negative'])}

        # Attendance
        att_agg = AttendanceRecord.objects.filter(
            student_id__in=student_ids, session__class_obj=class_obj
        ).values('student_id').annotate(
            total_sessions=Count('id'),
            present_count=Count('id', filter=Q(status__in=['present', 'late', 'excused', 'sick']))
        )
        att_dict = {}
        for item in att_agg:
            total = item['total_sessions']
            present = item['present_count']
            att_dict[item['student_id']] = {
                'summary': f"{present}/{total}" if total > 0 else "0/0",
                'percentage': (present / total * 100) if total > 0 else 0.0
            }

        # Academic: semua asesmen
        assessments = Assessment.objects.filter(class_obj=class_obj)
        total_max_points = assessments.aggregate(total=Sum('max_points'))['total'] or 0

        scores_qs = Score.objects.filter(student_id__in=student_ids, assessment__in=assessments)
        student_earned = {}
        for sc in scores_qs:
            student_earned[sc.student_id] = student_earned.get(sc.student_id, 0) + sc.points_earned

        acad_dict = {}
        for sid in student_ids:
            earned = student_earned.get(sid, 0)
            if total_max_points > 0:
                acad_dict[sid] = (earned / total_max_points) * 100
            else:
                acad_dict[sid] = 0.0

        # Skor per asesmen
        assessment_scores = {}
        if assessments:
            scores_for_table = Score.objects.filter(
                student_id__in=student_ids, assessment__in=assessments
            ).select_related('assessment')
            for sc in scores_for_table:
                key = (sc.student_id, sc.assessment_id)
                assessment_scores[key] = f"{sc.points_earned}/{sc.assessment.max_points}"

        # Bangun baris per siswa
        for idx, student in enumerate(students, 1):
            sid = student.id
            beh = beh_dict.get(sid, {'pos': 0, 'neg': 0})
            total_pos, total_neg = beh['pos'], beh['neg']
            net = total_pos - total_neg
            att_data = att_dict.get(sid, {'summary': '0/0', 'percentage': 0.0})
            att_pct = att_data['percentage']
            acad_avg = acad_dict.get(sid, 0.0)

            pos_cap = class_obj.positive_behavior_cap or 1
            neg_cap = class_obj.negative_behavior_cap or 1
            pos_comp = min((total_pos / pos_cap) * 100, 100)
            neg_comp = max(100 - (abs(total_neg) / neg_cap) * 100, 0)
            final = acad_avg * 0.6 + att_pct * 0.15 + pos_comp * 0.15 + neg_comp * 0.1
            final = min(round(final, 1), 100.0)

            row = {
                'No': idx, 'Nama Siswa': student.name,
                'Kehadiran': att_data['summary'],
                'Kehadiran (%)': round(att_pct, 1),
                'Poin Positif': total_pos, 'Poin Negatif': total_neg, 'Net Poin': net,
                'Rata-rata Akademik': round(acad_avg, 1), 'Final Score': final,
            }
            for ass in assessments:
                key = (sid, ass.id)
                row[ass.name] = assessment_scores.get(key, '-')
            data.append(row)

    # ===== PERBAIKAN: Cek library sebelum membuat Excel =====
    try:
        import pandas as pd
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        messages.error(
            request,
            "Fitur Export Excel memerlukan library pandas dan openpyxl. "
            "Silakan instal dengan perintah: pip install pandas openpyxl"
        )
        return redirect('dashboard')

    df = pd.DataFrame(data)
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{class_obj.name}_data.xlsx"'

    with pd.ExcelWriter(response, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Data Kelas', index=False)
        workbook = writer.book
        worksheet = writer.sheets['Data Kelas']

        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="2C3E50", end_color="2C3E50", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center")
        even_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
        thin_border = Border(left=Side(style='thin'), right=Side(style='thin'),
                             top=Side(style='thin'), bottom=Side(style='thin'))

        for col_idx, col_name in enumerate(df.columns, 1):
            cell = worksheet.cell(row=1, column=col_idx)
            cell.font, cell.fill, cell.alignment, cell.border = header_font, header_fill, header_alignment, thin_border

        for row_idx in range(2, len(df) + 2):
            for col_idx in range(1, len(df.columns) + 1):
                cell = worksheet.cell(row=row_idx, column=col_idx)
                cell.border = thin_border
                if row_idx % 2 == 0:
                    cell.fill = even_fill
                if col_idx in [1, 3, 4, 5, 6, 7, 8, 9]:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif col_idx == 2:
                    cell.alignment = Alignment(horizontal="left", vertical="center")
                else:
                    cell.alignment = Alignment(horizontal="center", vertical="center")

        for col_idx, col_name in enumerate(df.columns, 1):
            max_length = len(str(col_name))
            for row_idx in range(2, len(df) + 2):
                val = worksheet.cell(row=row_idx, column=col_idx).value
                if val:
                    max_length = max(max_length, len(str(val)))
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[get_column_letter(col_idx)].width = adjusted_width

        worksheet.row_dimensions[1].height = 20

        footer_row = len(df) + 3
        worksheet.cell(row=footer_row, column=1, value=f"Laporan Kelas: {class_obj.name}")
        worksheet.cell(row=footer_row+1, column=1, value=f"Guru: {request.user.username}")
        worksheet.cell(row=footer_row+2, column=1, value=f"Tanggal Export: {datetime.now().strftime('%d %B %Y %H:%M:%S')}")
        worksheet.cell(row=footer_row+3, column=1, value=f"Total Siswa: {len(students)}")
        for i in range(4):
            cell = worksheet.cell(row=footer_row + i, column=1)
            cell.font = Font(italic=True, color="7F8C8D")
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

import secrets

@login_required
def generate_parent_code(request, student_id):
    """Menghasilkan (atau mereset) kode akses orang tua untuk seorang siswa."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Metode tidak diizinkan.'}, status=405)

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Profil tidak ditemukan.'}, status=403)

    if profile.role != 'teacher':
        return JsonResponse({'status': 'error', 'message': 'Hanya guru yang bisa.'}, status=403)

    try:
        student = Student.objects.get(id=student_id)
    except Student.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Siswa tidak ditemukan.'}, status=404)

    # Buat kode acak 8 karakter
    new_code = secrets.token_urlsafe(6)[:8]  # 8 karakter cukup
    student.parent_code = new_code
    student.save()

    return JsonResponse({
        'status': 'ok',
        'code': new_code,
        'message': f'Kode akses untuk {student.name} berhasil dibuat.'
    })

from django.contrib import messages as django_messages

def parent_login(request):
    """Halaman login orang tua (hanya dengan kode akses)"""
    # Kuras semua pesan lama yang mungkin terbawa dari session lain
    storage = django_messages.get_messages(request)
    list(storage)   # mengiterasi semua pesan dan menandainya sebagai "used"
    # Alternatif: storage.used = True  juga bisa

    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        if not code:
            django_messages.error(request, 'Please enter an access code.')
            return redirect('parent_login')

        try:
            student = Student.objects.get(parent_code=code, is_active=True)
        except Student.DoesNotExist:
            django_messages.error(request, 'Invalid code or student is no longer active.')
            return redirect('parent_login')

        # Simpan student_id di session
        request.session['parent_student_id'] = student.id
        return redirect('parent_dashboard')

    return render(request, 'lms/parent_login.html')


def parent_dashboard(request):
    """Halaman dashboard orang tua setelah login"""
    student_id = request.session.get('parent_student_id')
    if not student_id:
        return redirect('parent_login')

    try:
        student = Student.objects.get(id=student_id, is_active=True)
    except Student.DoesNotExist:
        request.session.pop('parent_student_id', None)
        messages.error(request, 'Siswa tidak ditemukan.')
        return redirect('parent_login')

    # --- Data Kehadiran (30 hari terakhir) ---
    from datetime import date, timedelta
    thirty_days_ago = date.today() - timedelta(days=30)

    # Ambil semua sesi kehadiran untuk kelas-kelas yang diikuti siswa
    class_ids = Enrollment.objects.filter(student=student, is_active=True).values_list('class_obj_id', flat=True)
    attendance_sessions = AttendanceSession.objects.filter(
        class_obj_id__in=class_ids,
        date__gte=thirty_days_ago
    ).order_by('-date')

    records = AttendanceRecord.objects.filter(
        student=student,
        session__in=attendance_sessions
    ).select_related('session')

    status_dict = {r.session_id: r.get_status_display() for r in records}
    attendance_days = []
    for session in attendance_sessions:
        status = status_dict.get(session.id, '—')
        if status != '—':
            attendance_days.append({
                'date': session.date,
                'status': status_dict.get(session.id, '—')
            })

    # Hitung statistik kehadiran 30 hari
    total_sessions = len(attendance_sessions)
    present_count = sum(1 for s in attendance_sessions if status_dict.get(s.id) in ['Present', 'Late', 'Excused', 'Sick'])
    attendance_percent = (present_count / total_sessions * 100) if total_sessions > 0 else 0

    # --- Poin Perilaku Minggu Ini ---
    one_week_ago = timezone.now() - timedelta(days=7)
    recent_behaviors = BehaviorEntry.objects.filter(
        student=student,
        timestamp__gte=one_week_ago
    )
    pos_weekly = recent_behaviors.filter(points__gt=0).aggregate(total=Sum('points'))['total'] or 0
    neg_weekly = abs(recent_behaviors.filter(points__lt=0).aggregate(total=Sum('points'))['total'] or 0)

    # --- Feedback Terbaru (tetap diambil, tapi tidak ditampilkan di template) ---
    latest_feedback = StudentFeedback.objects.filter(
        student=student
    ).order_by('-last_updated').first()

    # --- Grafik Perkembangan Nilai (5 asesmen terakhir) ---
    scores = Score.objects.filter(student=student).select_related('assessment').order_by('-assessment__date')[:5]
    chart_labels = []
    chart_data = []
    for sc in reversed(scores):
        chart_labels.append(sc.assessment.name[:20])
        pct = (sc.points_earned / sc.assessment.max_points) * 100
        chart_data.append(round(pct, 1))

    # ---------- HITUNG FINAL SCORE (GABUNGAN SEMUA KELAS) ----------
    enrollments = Enrollment.objects.filter(student=student, is_active=True)
    classes = Class.objects.filter(id__in=class_ids)

    total_max_all = 0
    total_earned_all = 0
    for cls in classes:
        assessments = Assessment.objects.filter(class_obj=cls)
        total_max = assessments.aggregate(total=Sum('max_points'))['total'] or 0
        total_max_all += total_max
        scores = Score.objects.filter(student=student, assessment__in=assessments)
        earned = scores.aggregate(total=Sum('points_earned'))['total'] or 0
        total_earned_all += earned

    if total_max_all > 0:
        academic_avg = (total_earned_all / total_max_all) * 100
    else:
        academic_avg = 0.0

    first_enrollment = enrollments.first()
    if first_enrollment:
        pos_cap = first_enrollment.class_obj.positive_behavior_cap or 1
        neg_cap = first_enrollment.class_obj.negative_behavior_cap or 1
    else:
        pos_cap = 1
        neg_cap = 1

    positive_component = min((pos_weekly / pos_cap) * 100, 100) if pos_weekly > 0 else 0
    negative_component = max(100 - (abs(neg_weekly) / neg_cap) * 100, 0) if neg_weekly > 0 else 100

    final_score = (
        academic_avg * 0.6 + attendance_percent * 0.15 + positive_component * 0.15 + negative_component * 0.1
    )
    final_score = min(round(final_score, 1), 100.0) if total_max_all > 0 else None

    context = {
        'student': student,
        'attendance_days': attendance_days,
        'attendance_percent': round(attendance_percent, 1),
        'total_sessions': total_sessions,
        'present_count': present_count,
        'pos_weekly': pos_weekly,
        'neg_weekly': neg_weekly,
        'final_score': final_score,
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data),
        'latest_feedback': latest_feedback,
    }
    return render(request, 'lms/parent_dashboard.html', context)

def parent_logout(request):
    """Logout orang tua, hapus session."""
    request.session.pop('parent_student_id', None)
    return redirect('parent_login')

@login_required
def download_parent_codes(request, class_id):
    """Mengunduh daftar kode akses orang tua dalam format Excel (XLSX) yang rapi.
    Setiap siswa otomatis mendapatkan kode jika belum memiliki."""

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

    import secrets
    data = []

    for idx, enrollment in enumerate(enrollments, 1):
        student = enrollment.student

        # Jika belum memiliki kode, buatkan otomatis
        if not student.parent_code:
            student.parent_code = secrets.token_urlsafe(6)[:8]
            student.save()

        data.append({
            'No.': idx,
            'Student Name': student.name,
            'Parent Access Code': student.parent_code
        })

    if not data:
        messages.warning(request, "No students found in this class.")
        return redirect('dashboard')

    # Buat DataFrame
    import pandas as pd
    df = pd.DataFrame(data)

    # Siapkan response Excel
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="Parent_Codes_{class_obj.name.replace(' ', '_')}.xlsx"'

    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter

    with pd.ExcelWriter(response, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Parent Codes', index=False)
        workbook = writer.book
        worksheet = writer.sheets['Parent Codes']

        # Gaya header
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="2C3E50", end_color="2C3E50", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center")

        # Gaya isi
        thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # Format header
        for col_idx, col_name in enumerate(df.columns, 1):
            cell = worksheet.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            cell.border = thin_border

        # Format isi
        for row_idx in range(2, len(df) + 2):
            for col_idx in range(1, len(df.columns) + 1):
                cell = worksheet.cell(row=row_idx, column=col_idx)
                cell.border = thin_border

                if col_idx == 1:   # No.
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif col_idx == 2: # Nama
                    cell.alignment = Alignment(horizontal="left", vertical="center")
                elif col_idx == 3: # Kode
                    cell.alignment = Alignment(horizontal="center", vertical="center")

        # Lebar kolom
        col_widths = [6, 30, 22]
        for i, width in enumerate(col_widths, 1):
            worksheet.column_dimensions[get_column_letter(i)].width = width

        worksheet.row_dimensions[1].height = 20

    return response

import os
from django.conf import settings
from django.core.files.storage import default_storage

@login_required
def backup_database(request):
    """Mengunduh file database SQLite sebagai backup."""
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return HttpResponse("Profile missing.", status=403)
    if profile.role != 'teacher':
        return HttpResponse("Access restricted.", status=403)

    db_path = os.path.abspath(settings.DATABASES['default']['NAME'])
    if not os.path.exists(db_path):
        return HttpResponse("Database file not found.", status=404)

    with open(db_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type='application/octet-stream')
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        filename = f"backup_db_{timestamp}.sqlite3"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


import os
import shutil
import sqlite3
from datetime import datetime
from django.conf import settings
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

@login_required
def restore_database(request):
    """Menerima upload file database untuk me-restore data dengan aman."""
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

    db_path = settings.DATABASES['default']['NAME']
    if not os.path.isabs(db_path):
        db_path = os.path.abspath(db_path)

    # ---- 1. Validasi file yang diupload (cek apakah bisa dibuka sebagai SQLite) ----
    temp_path = db_path + '.restore_temp'
    try:
        with open(temp_path, 'wb+') as dest:
            for chunk in uploaded_file.chunks():
                dest.write(chunk)
        
        # Coba buka sebagai SQLite
        conn = sqlite3.connect(temp_path)
        conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        conn.close()
    except Exception as e:
        # Bersihkan file sementara jika gagal
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return JsonResponse({'status': 'error', 'message': f'Uploaded file is not a valid SQLite database: {str(e)}'})

    # ---- 2. Buat backup database saat ini sebelum menimpa ----
    backup_dir = os.path.join(settings.BASE_DIR, 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(backup_dir, f'backup_before_restore_{timestamp}.sqlite3')
    try:
        if os.path.exists(db_path):
            shutil.copy2(db_path, backup_path)
    except Exception as e:
        # Gagal backup jangan hentikan proses, tapi beri peringatan di log
        print(f"Warning: Could not create backup before restore: {e}")

    # ---- 3. Ganti file database secara atomik ----
    try:
        os.replace(temp_path, db_path)  # atomic pada sistem file yang sama
        return JsonResponse({
            'status': 'ok',
            'message': 'Database restored successfully. Please restart the server manually to apply changes fully.',
            'backup_created': os.path.basename(backup_path) if os.path.exists(backup_path) else None
        })
    except Exception as e:
        # Jika gagal mengganti, bersihkan temp
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return JsonResponse({'status': 'error', 'message': f'Failed to replace database: {str(e)}'})
    
from django.core.files.uploadedfile import InMemoryUploadedFile
import io

@login_required
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

    # Validasi ukuran (opsional, maks 2 MB)
    if uploaded_file.size > 2 * 1024 * 1024:
        return JsonResponse({'status': 'error', 'message': 'File terlalu besar. Maksimal 2 MB.'})

    # Validasi dengan PIL (import lokal)
    try:
        from PIL import Image as PILImage
        img = PILImage.open(uploaded_file)
        img.verify()                     # pastikan file adalah gambar valid
        uploaded_file.seek(0)
        img = PILImage.open(uploaded_file)
        if img.format not in ('JPEG', 'PNG', 'WEBP'):
            return JsonResponse({'status': 'error', 'message': 'Format gambar harus JPG, PNG, atau WEBP.'})
    except ImportError:
        return JsonResponse({'status': 'error', 'message': 'Server tidak mendukung pemrosesan gambar (Pillow belum terpasang).'}, status=500)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': 'File bukan gambar yang valid atau rusak.'})

    # Hapus foto lama jika ada
    if profile.profile_picture:
        profile.profile_picture.delete(save=False)

    uploaded_file.seek(0)  # reset posisi baca
    profile.profile_picture = uploaded_file
    profile.save()

    return JsonResponse({
        'status': 'ok',
        'message': 'Foto profil berhasil diperbarui.',
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
def sidebar_info(request):
    import os
    from datetime import datetime

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'Profile missing'}, status=403)

    # Semua kelas guru
    classes_to_check = Class.objects.filter(teacher=request.user)

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

    backup_dir = os.path.join(settings.BASE_DIR, 'backups')
    last_backup = None
    if os.path.exists(backup_dir):
        files = [f for f in os.listdir(backup_dir) if f.endswith('.sqlite3')]
        if files:
            latest_file = max(files, key=lambda f: os.path.getmtime(os.path.join(backup_dir, f)))
            mtime = os.path.getmtime(os.path.join(backup_dir, latest_file))
            last_backup = datetime.fromtimestamp(mtime).strftime('%d %b %Y, %H:%M')

    return JsonResponse({
        'class_count': class_count,
        'title': title,
        'last_backup': last_backup,
        'missing_assessments_count': missing_count,
        'first_missing_class_id': first_missing_class_id,
        'pending_by_class': pending_by_class,
    })