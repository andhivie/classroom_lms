@echo off
setlocal enabledelayedexpansion

:: Pindah ke folder proyek
cd /d C:\Users\yuolaff\Desktop\classroom_lms

:: Tentukan folder backup
set BACKUP_DIR=backups
if not exist %BACKUP_DIR% mkdir %BACKUP_DIR%

:: Nama file backup dengan timestamp
set TIMESTAMP=%DATE:/=-%_%TIME::=.%
set TIMESTAMP=%TIMESTAMP: =0%
set BACKUP_FILE=lms_backup_%TIMESTAMP%.sqlite3

:: Salin database
copy db.sqlite3 "%BACKUP_DIR%\%BACKUP_FILE%"

:: Hapus backup yang lebih lama dari 7 hari
forfiles /p "%BACKUP_DIR%" /m "lms_backup_*.sqlite3" /d -7 /c "cmd /c del @file" 2>nul

echo %DATE% %TIME% - Backup selesai: %BACKUP_FILE% >> backup_log.txt