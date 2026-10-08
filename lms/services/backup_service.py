"""
Centralized backup utilities for Classroom LMS.

All backup operations (manual, automatic, pre-restore) go through here.
Uses SQLite's native backup API for safe concurrent reads.
"""
import os
import sqlite3
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone


def _get_backup_dir():
    """Return the backups/ folder path, creating it if needed."""
    backup_dir = os.path.join(settings.BASE_DIR, 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def _get_db_path():
    """Return the absolute path to the SQLite DB."""
    db_path = str(settings.DATABASES['default']['NAME'])
    if not os.path.isabs(db_path):
        db_path = os.path.abspath(db_path)
    return db_path


def _rotate_backups(backup_dir, retention):
    """
    Delete old backups so only the latest `retention` remain.
    Files with 'pre_' in the name (pre-restore, pre-reset) are NEVER auto-deleted.
    """
    if retention <= 0:
        return

    files = []
    for f in os.listdir(backup_dir):
        if not f.endswith('.sqlite3'):
            continue
        # Skip critical backups
        if '_pre_' in f or f.startswith('lms_pre_'):
            continue
        full_path = os.path.join(backup_dir, f)
        try:
            files.append((f, os.path.getmtime(full_path), full_path))
        except OSError:
            continue

    files.sort(key=lambda x: x[1], reverse=True)

    to_delete = files[retention:]
    for fname, _, full_path in to_delete:
        try:
            os.remove(full_path)
        except OSError:
            pass


def create_backup(reason='manual', rotate=True):
    """
    Create a database backup.

    Args:
        reason: 'manual' | 'auto' | 'pre_restore' | 'pre_reset_class' | ...
                Used in filename so you can identify why it was made.
        rotate: If True, apply rolling window cleanup.

    Returns:
        dict with keys: success, filename, path, timestamp, reason, size_kb, error
    """
    db_path = _get_db_path()

    if not os.path.exists(db_path):
        return {
            'success': False,
            'error': 'Database file not found.',
        }

    backup_dir = _get_backup_dir()
    now = datetime.now()
    timestamp_str = now.strftime('%Y-%m-%d_%H-%M-%S')
    filename = f"lms_{reason}_{timestamp_str}.sqlite3"
    backup_path = os.path.join(backup_dir, filename)

    try:
        # SQLite native backup API — safe even with concurrent writes
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(backup_path)
        with dst:
            src.backup(dst)
        dst.close()
        src.close()
    except Exception as e:
        return {
            'success': False,
            'error': f'Backup failed: {e}',
        }

    # Ensure mtime is now (some filesystems cache)
    try:
        os.utime(backup_path, None)
    except OSError:
        pass

    if rotate:
        retention = int(getattr(settings, 'AUTO_BACKUP_RETENTION', 14))
        _rotate_backups(backup_dir, retention)

    try:
        size_kb = round(os.path.getsize(backup_path) / 1024, 1)
    except OSError:
        size_kb = 0

    return {
        'success': True,
        'filename': filename,
        'path': backup_path,
        'timestamp': now.strftime('%d %b %Y, %H:%M'),
        'reason': reason,
        'size_kb': size_kb,
    }


def get_backup_status():
    """
    Return status info about backups.

    Returns:
        dict:
            last_backup (datetime or None)
            last_backup_str (str or 'Never')
            age_hours (float or None)
            count (int)
            health ('healthy' | 'warning' | 'old' | 'none')
            total_size_kb (float)
    """
    backup_dir = _get_backup_dir()
    now = timezone.now()

    if not os.path.exists(backup_dir):
        return {
            'last_backup': None,
            'last_backup_str': 'Never',
            'age_hours': None,
            'count': 0,
            'health': 'none',
            'total_size_kb': 0,
        }

    files = [f for f in os.listdir(backup_dir) if f.endswith('.sqlite3')]
    if not files:
        return {
            'last_backup': None,
            'last_backup_str': 'Never',
            'age_hours': None,
            'count': 0,
            'health': 'none',
            'total_size_kb': 0,
        }

    # Find latest by mtime
    latest_file = None
    latest_mtime = 0
    total_size = 0
    for f in files:
        full_path = os.path.join(backup_dir, f)
        try:
            mtime = os.path.getmtime(full_path)
            total_size += os.path.getsize(full_path)
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_file = f
        except OSError:
            continue

    if not latest_file:
        return {
            'last_backup': None,
            'last_backup_str': 'Never',
            'age_hours': None,
            'count': len(files),
            'health': 'none',
            'total_size_kb': 0,
        }

    # Convert mtime → aware datetime
    last_backup_dt = timezone.make_aware(datetime.fromtimestamp(latest_mtime))
    age = now - last_backup_dt
    age_hours = age.total_seconds() / 3600

    # Health check
    interval_hours = int(getattr(settings, 'AUTO_BACKUP_INTERVAL_HOURS', 24))
    warning_threshold = interval_hours * 1.5   # 1.5× interval
    old_threshold = interval_hours * 3          # 3× interval

    if age_hours < warning_threshold:
        health = 'healthy'
    elif age_hours < old_threshold:
        health = 'warning'
    else:
        health = 'old'

    return {
        'last_backup': last_backup_dt,
        'last_backup_str': last_backup_dt.strftime('%d %b %Y, %H:%M'),
        'age_hours': round(age_hours, 1),
        'count': len(files),
        'health': health,
        'total_size_kb': round(total_size / 1024, 1),
    }