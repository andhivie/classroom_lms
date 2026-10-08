"""
Management command: auto_backup

Creates a database backup and rotates old ones. Can be called:
  - Manually:      python manage.py auto_backup
  - Via scheduler: cron / Windows Task Scheduler
"""
from django.core.management.base import BaseCommand
from lms.services.backup_service import create_backup, get_backup_status


class Command(BaseCommand):
    help = "Create an automatic database backup and rotate old backups."

    def add_arguments(self, parser):
        parser.add_argument(
            '--reason',
            type=str,
            default='auto',
            help="Reason label for the backup filename (default: auto).",
        )
        parser.add_argument(
            '--quiet',
            action='store_true',
            help="Only print errors, no success output.",
        )

    def handle(self, *args, **options):
        reason = options['reason']
        quiet = options['quiet']

        result = create_backup(reason=reason, rotate=True)

        if not result['success']:
            self.stderr.write(self.style.ERROR(f"Backup failed: {result.get('error')}"))
            return

        if not quiet:
            self.stdout.write(self.style.SUCCESS(
                f"Backup created: {result['filename']}"
            ))
            self.stdout.write(f"  Path:   {result['path']}")
            self.stdout.write(f"  Size:   {result.get('size_kb', 0)} KB")
            self.stdout.write(f"  Reason: {result['reason']}")

            status = get_backup_status()
            self.stdout.write(f"  Total backups kept: {status['count']}")