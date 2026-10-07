from django.db import migrations


def clamp_behavior_points(apps, schema_editor):
    """
    Convert legacy behavior point values to the new scale.
    Legacy: +5 positive, -3 negative.
    New: +3 positive, -3 negative.
    """
    BehaviorEntry = apps.get_model('lms', 'BehaviorEntry')
    updated_pos = BehaviorEntry.objects.filter(points=5).update(points=3)
    print(f"  Clamped {updated_pos} entries from +5 to +3")


def reverse_clamp(apps, schema_editor):
    """
    Reverse: +3 -> +5. Note: this will incorrectly reverse any
    legitimately new +3 entries. Use only for rollback during development.
    """
    BehaviorEntry = apps.get_model('lms', 'BehaviorEntry')
    updated = BehaviorEntry.objects.filter(points=3).update(points=5)
    print(f"  Reverted {updated} entries from +3 to +5")


class Migration(migrations.Migration):

    dependencies = [
        ('lms', '0007_behaviorentry_semester_class_bonus_per_conversion_and_more'),
    ]

    operations = [
        migrations.RunPython(clamp_behavior_points, reverse_clamp),
    ]