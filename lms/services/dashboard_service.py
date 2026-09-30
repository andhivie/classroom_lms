from django.db.models import Sum, Count, Q, Value
from django.db.models.functions import Coalesce

from lms.models import (
    BehaviorEntry,
    AttendanceRecord,
)


def get_behavior_summary(student_ids):
    """
    Mengembalikan ringkasan poin perilaku setiap siswa.

    Return:
    {
        student_id: {
            total_positive,
            total_negative,
            net_points
        }
    }
    """

    behavior_agg = (
        BehaviorEntry.objects
        .filter(student_id__in=student_ids)
        .values("student_id")
        .annotate(
            total_positive=Coalesce(
                Sum("points", filter=Q(points__gt=0)),
                Value(0)
            ),
            total_negative=Coalesce(
                Sum("points", filter=Q(points__lt=0)),
                Value(0)
            ),
        )
    )

    return {
        item["student_id"]: {
            "total_positive": item["total_positive"],
            "total_negative": abs(item["total_negative"]),
            "net_points": item["total_positive"] + item["total_negative"],
        }
        for item in behavior_agg
    }

def get_attendance_summary(student_ids, class_obj):
    attendance_agg = (
        AttendanceRecord.objects
        .filter(
            student_id__in=student_ids,
            session__class_obj=class_obj
        )
        .values("student_id")
        .annotate(
            total_sessions=Count("id"),
            present_count=Count(
                "id",
                filter=Q(
                    status__in=[
                        "present",
                        "late",
                        "excused",
                        "sick",
                    ]
                )
            ),
        )
    )

    attendance_dict = {}

    for item in attendance_agg:

        total = item["total_sessions"]
        present = item["present_count"]

        attendance_dict[item["student_id"]] = {
            "total_sessions": total,
            "present_count": present,
            "percentage": (
                (present / total) * 100
                if total > 0 else 0
            ),
        }

    return attendance_dict

def calculate_final_score(
    academic_avg,
    attendance_percentage,
    total_positive,
    total_negative,
    cls,
    has_behavior,
):
    """
    Menghitung nilai akhir dashboard.
    """

    if not has_behavior:
        positive_component = 0
        negative_component = 100
    else:
        pos_cap = cls.positive_behavior_cap or 1
        neg_cap = cls.negative_behavior_cap or 1

        positive_component = min(
            (total_positive / pos_cap) * 100,
            100
        )

        negative_component = max(
            100 - (abs(total_negative) / neg_cap) * 100,
            0
        )

    final_score = (
        academic_avg * 0.60
        + attendance_percentage * 0.15
        + positive_component * 0.15
        + negative_component * 0.10
    )

    return min(round(final_score, 1), 100.0)

def build_dashboard_data(
    teacher,
    selected_class_id=None,
    search_query="",
):
    """
    Membangun seluruh data dashboard guru.

    Untuk sementara fungsi ini masih kosong.
    Pada langkah berikutnya seluruh logika dashboard
    akan dipindahkan ke sini.
    """

    raise NotImplementedError(
        "build_dashboard_data() belum diimplementasikan."
    )