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
    window.showNotification = function(message, type) {
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

// --- Activity Log ---
function addActivityLog(action) {
    const now = new Date();
    const timeStr = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    const logs = JSON.parse(localStorage.getItem('activityLog') || '[]');
    logs.unshift({ action, time: timeStr });
    if (logs.length > 20) logs.pop();
    localStorage.setItem('activityLog', JSON.stringify(logs));

    const logContainer = document.getElementById('recentActivityList');
    if (logContainer) {
        logContainer.innerHTML = '';
        logs.slice(0, 3).forEach(log => {
            logContainer.innerHTML += `
                <div class="py-1">
                    <i class="bi bi-dot me-1"></i> ${log.action}
                    <span class="text-muted ms-1">(${log.time})</span>
                </div>`;
        });
    }
}
window.addActivityLog = addActivityLog;

// --- Fungsi update sidebar info & pending assessments ---
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
        // Ringkasan
        if (data.class_count !== undefined) {
            const el = document.getElementById('sidebarClassCount');
            if (el) el.textContent = data.class_count;
        }
        if (data.title) {
            const el = document.getElementById('sidebarTitle');
            if (el) el.textContent = data.title;
        }
        if (data.last_backup) {
            const el = document.getElementById('sidebarLastBackup');
            if (el) el.textContent = data.last_backup;
        } else {
            const el = document.getElementById('sidebarLastBackup');
            if (el) el.textContent = 'Never';
        }

        // Notifikasi Asesmen Pending
        const wrapper = document.getElementById('missingAssessmentsWrapper');
        const badge = document.getElementById('notificationBadge');
        const link = document.getElementById('missingAssessmentsLink');
        const dropdown = document.getElementById('pendingClassDropdown');

        if (wrapper && badge && link && dropdown) {
            const count = data.missing_assessments_count || 0;
            badge.textContent = count;

            // Hapus instance Bootstrap lama
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
                        a.style.display = 'flex';
                        a.style.justifyContent = 'space-between';
                        a.style.alignItems = 'center';
                        a.style.fontSize = '0.86rem';
                        a.style.padding = '0.3rem 0.8rem';
                        li.appendChild(a);
                        dropdown.appendChild(li);
                    });
                }

                // Inisialisasi dropdown baru
                link.setAttribute('data-bs-toggle', 'dropdown');
                link.classList.add('dropdown-toggle');
                new bootstrap.Dropdown(link);
            } else {
                wrapper.style.display = 'block';
                link.classList.add('disabled');
                link.style.pointerEvents = 'none';
                link.style.opacity = '0.6';
                dropdown.innerHTML = '';
            }
        }

        // Log Aktivitas (localStorage)
        const logs = JSON.parse(localStorage.getItem('activityLog') || '[]');
        const logContainer = document.getElementById('recentActivityList');
        if (logContainer) {
            logContainer.innerHTML = '';
            if (logs.length === 0) {
                logContainer.innerHTML = '<div class="py-1"><i class="bi bi-info-circle me-1"></i> No recent activity</div>';
            } else {
                logs.slice(0, 3).forEach(log => {
                    logContainer.innerHTML += `<div class="py-1"><i class="bi bi-dot me-1"></i> ${log.action} <span class="text-muted ms-1">(${log.time})</span></div>`;
                });
            }
        }
    })
    .catch(err => console.error('Sidebar info error:', err));
}
window.updateSidebarInfo = updateSidebarInfo;

// --- Profile Picture ---
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
            preview.innerHTML = `<img src="${data.image_url}" class="rounded-circle mb-2" width="80" height="80" style="object-fit: cover;">`;
            const uploadText = document.getElementById('uploadBtnText');
            if (uploadText) uploadText.textContent = ' Change';
            const actionsDiv = document.getElementById('profilePicActions');
            if (!document.getElementById('deleteProfilePicBtn')) {
                const removeBtn = document.createElement('button');
                removeBtn.id = 'deleteProfilePicBtn';
                removeBtn.className = 'btn btn-sm btn-outline-danger ms-1';
                removeBtn.innerHTML = '<i class="bi bi-trash"></i> Remove';
                removeBtn.addEventListener('click', deleteProfilePic);
                actionsDiv.appendChild(removeBtn);
            }
            showNotification('Profile picture updated.', 'success');
        } else {
            showNotification(data.message, 'danger');
        }
    })
    .catch(err => {
        console.error(err);
        showNotification('Upload failed.', 'danger');
    })
    .finally(() => { input.value = ''; });
}

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
            preview.innerHTML = '<i class="bi bi-person-circle" style="font-size: 4rem; color: #003f5c;"></i>';
            const uploadText = document.getElementById('uploadBtnText');
            if (uploadText) uploadText.textContent = ' Upload';
            const removeBtn = document.getElementById('deleteProfilePicBtn');
            if (removeBtn) removeBtn.remove();
            showNotification('Profile picture removed.', 'success');
        } else {
            showNotification(data.message, 'danger');
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

document.addEventListener('DOMContentLoaded', function() {
    restoreModal = new bootstrap.Modal(document.getElementById('restoreConfirmModal'));
});

if (restoreDatabaseBtn) {
    restoreDatabaseBtn.addEventListener('click', function() {
        restoreFileInput.click();
    });
}

if (restoreFileInput) {
    restoreFileInput.addEventListener('change', function() {
        if (restoreFileInput.files.length > 0) restoreModal.show();
    });
}

if (confirmRestoreBtn) {
    confirmRestoreBtn.addEventListener('click', function() {
        const file = restoreFileInput.files[0];
        if (!file) {
            showNotification('Please select a backup file first.', 'warning');
            return;
        }

        const formData = new FormData();
        formData.append('database', file);

        fetch('/restore-database/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: formData
        })
        .then(res => res.json())
        .then(data => {
            const statusDiv = document.getElementById('restoreStatus');
            if (data.status === 'ok') {
                statusDiv.innerHTML = '<div class="alert alert-success py-2 small">✅ ' + data.message + '</div>';
                addActivityLog('Database restored');
            } else {
                statusDiv.innerHTML = '<div class="alert alert-danger py-2 small">❌ ' + data.message + '</div>';
            }
            restoreModal.hide();
        })
        .catch(err => {
            console.error(err);
            document.getElementById('restoreStatus').innerHTML = '<div class="alert alert-danger py-2 small">Network error.</div>';
        })
        .finally(() => { restoreFileInput.value = ''; });
    });
}

document.getElementById('restoreConfirmModal')?.addEventListener('hidden.bs.modal', function() {
    restoreFileInput.value = '';
});

// --- Event untuk membuka sidebar langsung memuat data ---
const sidebarEl = document.getElementById('sidebarOffcanvas');
if (sidebarEl) {
    sidebarEl.addEventListener('show.bs.offcanvas', updateSidebarInfo);
    sidebarEl.addEventListener('shown.bs.offcanvas', function() {
        setTimeout(updateSidebarInfo, 100);
    });
}

// --- Cegah sidebar menutup saat klik di dalamnya ---
if (sidebarEl) {
    // Hentikan propagasi klik di dalam sidebar agar tidak menutup offcanvas
    sidebarEl.addEventListener('click', function(e) {
        e.stopPropagation();
    });

    // Cegah offcanvas menutup jika dropdown Assessments Pending sedang terbuka
    sidebarEl.addEventListener('hide.bs.offcanvas', function(e) {
        const dropdownMenu = document.querySelector('#pendingClassDropdown.show');
        if (dropdownMenu) {
            e.preventDefault();
        }
    });
}

// --- Profile Pic Change Event ---
document.addEventListener('DOMContentLoaded', function() {
    const profilePicInput = document.getElementById('profilePicInput');
    if (profilePicInput) {
        profilePicInput.addEventListener('change', function() {
            uploadProfilePic(this);
        });
    }

    const delBtn = document.getElementById('deleteProfilePicBtn');
    if (delBtn) delBtn.addEventListener('click', deleteProfilePic);
});

// --- Log Backup ---
const backupBtn = document.getElementById('backupDatabaseBtn');
if (backupBtn) {
    backupBtn.addEventListener('click', function() {
        addActivityLog('Database backup downloaded');
    });
}

// ========== AUTO-UPDATE PERIODIK ==========
setInterval(function() {
    const offcanvas = document.getElementById('sidebarOffcanvas');
    if (offcanvas && offcanvas.classList.contains('show')) {
        updateSidebarInfo();
    }
}, 30000);