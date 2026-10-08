"""
Auto-backup middleware — lazy scheduler.

Every HTTP request triggers a lightweight check:
    "Has enough time passed since the last automatic backup?"

If yes → backup runs in a background thread (non-blocking).

This ensures backups happen even without an OS-level scheduler.
For production, still set up cron / Task Scheduler — this is a safety net.
"""
import threading
import logging
from datetime import datetime

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Cache key & lock to prevent duplicate checks
_CHECK_LOCK = threading.Lock()
_LAST_CHECK_CACHE_KEY = 'auto_backup_last_check'


class AutoBackupMiddleware:
    """
    Middleware that occasionally triggers automatic database backups.
    Silent by design — never blocks requests, never raises errors.
    """

    SKIP_PREFIXES = ('/static/', '/media/', '/favicon.ico', '/admin/jsi18n/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip static/media requests entirely
        if request.path.startswith(self.SKIP_PREFIXES):
            return self.get_response(request)

        # Only check every N minutes (not on every request)
        try:
            self._maybe_schedule_backup()
        except Exception:
            logger.exception("Auto backup middleware failed (non-fatal)")

        return self.get_response(request)

    def _maybe_schedule_backup(self):
        if not getattr(settings, 'AUTO_BACKUP_ENABLED', False):
            return

        # Rate-limit: don't check more than once every 5 minutes
        if cache.get(_LAST_CHECK_CACHE_KEY):
            return

        cache.set(_LAST_CHECK_CACHE_KEY, True, timeout=300)  # 5 min

        # Is it time for a new backup?
        from lms.services.backup_service import get_backup_status

        status = get_backup_status()
        interval_hours = int(getattr(settings, 'AUTO_BACKUP_INTERVAL_HOURS', 24))

        needs_backup = False
        if status['last_backup'] is None:
            needs_backup = True
        elif status['age_hours'] is not None and status['age_hours'] >= interval_hours:
            needs_backup = True

        if not needs_backup:
            return

        # Run in background thread to avoid blocking the request
        with _CHECK_LOCK:
            # Second check inside lock — avoid double-spawn
            status2 = get_backup_status()
            if status2['last_backup'] is not None and status2['age_hours'] is not None:
                if status2['age_hours'] < interval_hours:
                    return

            thread = threading.Thread(
                target=self._run_backup_in_background,
                daemon=True,
            )
            thread.start()

    @staticmethod
    def _run_backup_in_background():
        from lms.services.backup_service import create_backup
        try:
            result = create_backup(reason='auto', rotate=True)
            if result['success']:
                logger.info(f"Auto backup created: {result['filename']}")
            else:
                logger.warning(f"Auto backup failed: {result.get('error')}")
        except Exception:
            logger.exception("Auto backup thread crashed")