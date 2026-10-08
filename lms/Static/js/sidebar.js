// ======================== SIDEBAR FUNCTIONS ========================

// --- CSRF Token ---
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
const csrfToken = getCookie('csrftoken');

// --- Notifikasi (fallback) ---
if (typeof showNotification === 'undefined') {
    window.showNotification = function (message, type) {
        const notif = document.createElement('div');
        notif.className = `alert alert-${type} alert-dismissible fade show`;
        notif.style.position = 'fixed';
        notif.style.top = '70px';
        notif.style.right = '20px';
        notif.style.zIndex = '9999';
        notif.style.minWidth = '250px';
        notif.innerHTML = `${message}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
        document.body.appendChild(notif);
        setTimeout(() => notif.remove(), 4000);
    };
}

// --- Activity Log (database) ---
function addActivityLog(action) {
    if (!action) return;

    fetch('/activity-log/add/', {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrfToken,
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded'
        },
        body: new URLSearchParams({ action: action })
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'ok') {
            // Refresh sidebar info to pull updated recent_activity from DB
            updateSidebarInfo();
        }
    })
    .catch(err => console.error('Activity log error:', err));
}
window.addActivityLog = addActivityLog;

// --- Render activity log from server data ---
function renderActivityLog(logs) {
    const logContainer = document.getElementById('recentActivityList');
    if (!logContainer) return;

    logContainer.innerHTML = '';
    if (!logs || logs.length === 0) {
        logContainer.innerHTML = `
            <div class="activity-empty">
                <i class="bi bi-info-circle"></i>
                <span>No recent activity</span>
            </div>`;
        return;
    }

    logs.slice(0, 5).forEach(log => {
        logContainer.innerHTML += `
            <div class="activity-line">
                <i class="bi bi-dot"></i>
                <span>${escapeHtmlSidebar(log.action)}</span>
                <span class="activity-time">${log.time}</span>
            </div>`;
    });
}

// Escape helper (unique name to avoid conflict with dashboard.js)
function escapeHtmlSidebar(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

// --- Update sidebar info (stats + notifications + activity) ---
function updateSidebarInfo() {
    const urlParams = new URLSearchParams(window.location.search);
    const currentClassId = urlParams.get('class_id') || '';
    let fetchUrl = '/sidebar-info/';
    if (currentClassId) fetchUrl += '?class_id=' + currentClassId;

    fetch(fetchUrl, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
        .then(res => res.json())
        .then(data => {
            // ----- Stats -----
            if (data.class_count !== undefined) {
                const el = document.getElementById('sidebarClassCount');
                if (el) el.textContent = data.class_count;
            }
            if (data.title) {
                const el = document.getElementById('sidebarTitle');
                if (el) el.textContent = data.title;
            }
            const backupEl = document.getElementById('sidebarLastBackup');
            if (backupEl) {
                const health = data.backup_health || 'none';

                // Clear existing health classes
                backupEl.classList.remove(
                    'backup-status-healthy',
                    'backup-status-warning',
                    'backup-status-old',
                    'backup-status-none',
                    'backup-status-unknown'
                );

                if (data.last_backup) {
                    backupEl.textContent = data.last_backup;
                    backupEl.classList.add(`backup-status-${health}`);
                } else {
                    backupEl.textContent = 'Never';
                    backupEl.classList.add('backup-status-none');
                }
            }

            // ----- Notifications: missing assessments -----
            const wrapper = document.getElementById('missingAssessmentsWrapper');
            const badge = document.getElementById('notificationBadge');
            const link = document.getElementById('missingAssessmentsLink');
            const dropdown = document.getElementById('pendingClassDropdown');

            if (wrapper && badge && link && dropdown) {
                const count = data.missing_assessments_count || 0;
                badge.textContent = count;

                // Dispose any previous Bootstrap instances
                const oldDropdown = bootstrap.Dropdown.getInstance(link);
                if (oldDropdown) oldDropdown.dispose();
                const oldTip = bootstrap.Tooltip.getInstance(link);
                if (oldTip) oldTip.dispose();

                // Reset toggle
                link.removeAttribute('data-bs-toggle');
                link.classList.remove('dropdown-toggle');

                if (count > 0) {
                    wrapper.style.display = 'block';
                    link.classList.remove('disabled');
                    link.style.pointerEvents = 'auto';
                    link.style.opacity = '1';

                    dropdown.innerHTML = '';
                    if (data.pending_by_class && Object.keys(data.pending_by_class).length > 0) {
                        const entries = Object.entries(data.pending_by_class);
                        entries.sort((a, b) => a[1].name.localeCompare(b[1].name));
                        entries.forEach(([classId, info]) => {
                            const li = document.createElement('li');
                            const a = document.createElement('a');
                            a.className = 'dropdown-item pending-class-item';
                            a.href = `/class/${classId}/assessments/`;
                            a.innerHTML = `<span class="pending-class-name">${info.name}</span> <span class="badge bg-warning text-dark pending-count-badge">${info.count}</span>`;
                            li.appendChild(a);
                            dropdown.appendChild(li);
                        });
                    }

                    link.setAttribute('data-bs-toggle', 'dropdown');
                    link.classList.add('dropdown-toggle');
                    new bootstrap.Dropdown(link);
                } else {
                    wrapper.style.display = 'none';
                    link.classList.add('disabled');
                    link.style.pointerEvents = 'none';
                    link.style.opacity = '0.6';
                    dropdown.innerHTML = '';
                }
            }

            // ----- Recent activity (from server) -----
            renderActivityLog(data.recent_activity || []);
        })
        .catch(err => console.error('Sidebar info error:', err));
}
window.updateSidebarInfo = updateSidebarInfo;

// --- Profile Picture: Upload ---
function uploadProfilePic(input) {
    const file = input.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('profile_picture', file);

    fetch('/profile/upload-picture/', {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrfToken,
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: formData
    })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'ok') {
                const preview = document.getElementById('profilePicPreview');
                if (preview) {
                    preview.innerHTML = `<img src="${data.image_url}" alt="Profile picture">`;
                }
                const uploadText = document.getElementById('uploadBtnText');
                if (uploadText) uploadText.textContent = 'Change';

                const actionsDiv = document.getElementById('profilePicActions');
                if (actionsDiv && !document.getElementById('deleteProfilePicBtn')) {
                    const removeBtn = document.createElement('button');
                    removeBtn.id = 'deleteProfilePicBtn';
                    removeBtn.className = 'btn-profile-action btn-danger-soft';
                    removeBtn.innerHTML = '<i class="bi bi-trash"></i> Remove';
                    removeBtn.addEventListener('click', deleteProfilePic);
                    actionsDiv.appendChild(removeBtn);
                }

                showNotification('Profile picture updated.', 'success');
            } else {
                showNotification(data.message || 'Upload failed.', 'danger');
            }
        })
        .catch(err => {
            console.error(err);
            showNotification('Upload failed.', 'danger');
        })
        .finally(() => { input.value = ''; });
}

// --- Profile Picture: Delete ---
function deleteProfilePic() {
    if (!confirm('Remove profile picture?')) return;

    fetch('/profile/delete-picture/', {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrfToken,
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'ok') {
                const preview = document.getElementById('profilePicPreview');
                if (preview) {
                    preview.innerHTML = `
                        <div class="avatar-placeholder">
                            <i class="bi bi-person-fill"></i>
                        </div>`;
                }
                const uploadText = document.getElementById('uploadBtnText');
                if (uploadText) uploadText.textContent = 'Upload';

                const removeBtn = document.getElementById('deleteProfilePicBtn');
                if (removeBtn) removeBtn.remove();

                showNotification('Profile picture removed.', 'success');
            } else {
                showNotification(data.message || 'Failed.', 'danger');
            }
        })
        .catch(err => {
            console.error(err);
            showNotification('Failed to remove picture.', 'danger');
        });
}

// --- Restore Database ---
const restoreFileInput = document.getElementById('restoreFileInput');
const restoreDatabaseBtn = document.getElementById('restoreDatabaseBtn');
const confirmRestoreBtn = document.getElementById('confirmRestoreBtn');
let restoreModal;

// Simpan file yang dipilih di variabel global — jangan baca ulang dari input
let selectedRestoreFile = null;

document.addEventListener('DOMContentLoaded', function () {
    const restoreModalEl = document.getElementById('restoreConfirmModal');
    if (restoreModalEl) {
        restoreModal = new bootstrap.Modal(restoreModalEl);
    }
});

if (restoreDatabaseBtn) {
    restoreDatabaseBtn.addEventListener('click', function () {
        if (restoreFileInput) restoreFileInput.click();
    });
}

if (restoreFileInput) {
    restoreFileInput.addEventListener('change', function () {
        const file = restoreFileInput.files[0];
        if (!file) return;

        // Validate extension
        if (!file.name.toLowerCase().endsWith('.sqlite3')) {
            showNotification('Invalid file format. Must be .sqlite3', 'danger');
            restoreFileInput.value = '';
            return;
        }

        // Save file to global variable
        selectedRestoreFile = file;
        console.log('File selected for restore:', file.name, `(${Math.round(file.size / 1024)} KB)`);

        if (restoreModal) restoreModal.show();
    });
}

if (confirmRestoreBtn) {
    confirmRestoreBtn.addEventListener('click', function () {
        // Use the saved file, not the input value
        const file = selectedRestoreFile;

        if (!file) {
            showNotification('Please select a backup file first.', 'warning');
            if (restoreFileInput) restoreFileInput.click();
            return;
        }

        const formData = new FormData();
        formData.append('database', file, file.name);

        const btn = this;
        const originalHTML = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Restoring...';

        fetch('/restore-database/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: formData
        })
        .then(res => {
            if (!res.ok) {
                return res.json().then(data => {
                    throw new Error(data.message || 'Server error ' + res.status);
                }).catch(() => {
                    throw new Error('Server error ' + res.status);
                });
            }
            return res.json();
        })
        .then(data => {
            if (data.status === 'ok') {
                showNotification(data.message, 'success');
                addActivityLog('Database restored');
                selectedRestoreFile = null;
            } else {
                showNotification(data.message, 'danger');
            }
            if (restoreModal) restoreModal.hide();
        })
        .catch(err => {
            console.error('Restore error:', err);
            const errMsg = err.message || 'Network error.';
            showNotification(errMsg, 'danger');
        })
        .finally(() => {
            btn.disabled = false;
            btn.innerHTML = originalHTML;
            if (restoreFileInput) restoreFileInput.value = '';
            selectedRestoreFile = null;
        });
    });
}

// Reset file state only when modal is fully closed AND restore succeeded or user cancels
document.getElementById('restoreConfirmModal')?.addEventListener('hidden.bs.modal', function () {
    // If success, clear the file
    // If user cancels (dismissed), also clear
    if (restoreFileInput) restoreFileInput.value = '';
    selectedRestoreFile = null;
});

// --- Sidebar events: load info on open ---
const sidebarEl = document.getElementById('sidebarOffcanvas');
if (sidebarEl) {
    sidebarEl.addEventListener('show.bs.offcanvas', updateSidebarInfo);
    sidebarEl.addEventListener('shown.bs.offcanvas', function () {
        setTimeout(updateSidebarInfo, 100);
    });
}

// --- Prevent sidebar from closing when clicking inside ---
if (sidebarEl) {
    sidebarEl.addEventListener('click', function (e) {
        e.stopPropagation();
    });

    // Prevent offcanvas from closing if dropdown is open
    sidebarEl.addEventListener('hide.bs.offcanvas', function (e) {
        const dropdownMenu = document.querySelector('#pendingClassDropdown.show');
        if (dropdownMenu) {
            e.preventDefault();
        }
    });
}

// --- Profile Pic input listener ---
document.addEventListener('DOMContentLoaded', function () {
    const profilePicInput = document.getElementById('profilePicInput');
    if (profilePicInput) {
        profilePicInput.addEventListener('change', function () {
            uploadProfilePic(this);
        });
    }

    const delBtn = document.getElementById('deleteProfilePicBtn');
    if (delBtn) delBtn.addEventListener('click', deleteProfilePic);
});

// --- Backup Database (fetch + auto-refresh sidebar info) ---
const backupBtn = document.getElementById('backupDatabaseBtn');
if (backupBtn) {
    backupBtn.addEventListener('click', async function () {
        const btn = this;
        const originalHTML = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span><span class="item-label">Backing up...</span>';

        try {
            // Step 1: trigger backup on server (saves file + returns JSON)
            const infoRes = await fetch('/backup-database/?ajax=true', {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            const info = await infoRes.json();

            if (info.status !== 'ok') {
                throw new Error(info.message || 'Backup failed');
            }

            // Step 2: trigger actual file download
            const downloadLink = document.createElement('a');
            downloadLink.href = '/backup-database/';
            downloadLink.download = info.filename;
            document.body.appendChild(downloadLink);
            downloadLink.click();
            document.body.removeChild(downloadLink);

            // Step 3: update UI
            addActivityLog('Database backup downloaded');
            showNotification(`Backup saved: ${info.filename}`, 'success');

            // Step 4: refresh sidebar info (updates BACKUP stat)
            if (typeof updateSidebarInfo === 'function') {
                updateSidebarInfo();
            }
        } catch (err) {
            console.error(err);
            showNotification(err.message || 'Backup failed', 'danger');
        } finally {
            btn.disabled = false;
            btn.innerHTML = originalHTML;
        }
    });
}

// --- Auto-update sidebar info periodically ---
setInterval(function () {
    const offcanvas = document.getElementById('sidebarOffcanvas');
    if (offcanvas && offcanvas.classList.contains('show')) {
        updateSidebarInfo();
    }
}, 30000);