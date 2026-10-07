"""
Central constants for the LMS application.
"""

# ---------------------------------------------------------------------------
# Standard assessment types (Priority 2 requirement)
# ---------------------------------------------------------------------------
# Only these 6 types may be used when creating or editing an assessment.
# "Daily Test" is special: it is the only type that uses the
# min_points_for_daily_test rule from the class settings.
# ---------------------------------------------------------------------------

STANDARD_ASSESSMENT_TYPES = [
    'Daily Test',
    'Assignment',
    'Quiz',
    'Mid-term Exam',
    'Final Exam',
    'Project',
]

# The one type that triggers the Daily Test min-points requirement.
DAILY_TEST_TYPE = 'Daily Test'