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

// --- Live clock ---
function updateClock() {
    const now = new Date();
    const options = {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
    };
    const clockEl = document.getElementById('live-clock');
    if (clockEl) {
        clockEl.innerText = now.toLocaleDateString('en-US', options).replace(',', ' ·');
    }
}
window.updateClock = updateClock;
updateClock();
setInterval(updateClock, 60000);

// --- Notifikasi fallback ---
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

// --- Escape helper ---
function escapeHtmlSidebar(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

// --- Activity Log ---
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
        if (data.status === 'ok') updateSidebarInfo();
    })
    .catch(err => console.error('Activity log error:', err));
}
window.addActivityLog = addActivityLog;

// ============================================================
// NEEDS ATTENTION
// ============================================================
function renderNeedsAttention(list) {
    const container = document.getElementById('needsAttentionList');
    if (!container) return;

    container.innerHTML = '';

    if (!list || list.length === 0) {
        container.innerHTML = `
            <div class="focus-empty-state">
                <i class="bi bi-check-circle"></i>
                <span>All clear</span>
            </div>
        `;
        return;
    }

    list.forEach(item => {
        const a = document.createElement('a');
        a.href = '#';
        a.className = `alert-item alert-item-${item.severity}`;
        a.dataset.studentId = item.id;
        a.dataset.classId = item.class_id;

        const detailsHtml = item.details && item.details.length > 0
            ? `<div class="alert-item-details">${item.details.slice(0, 2).map(d => `• ${escapeHtmlSidebar(d)}`).join('<br>')}</div>`
            : '';

        a.innerHTML = `
            <div class="alert-item-header">
                <span class="alert-item-name">${escapeHtmlSidebar(item.name)}</span>
                <span class="alert-item-count">${item.count}</span>
            </div>
            <div class="alert-item-class">${escapeHtmlSidebar(item.class_name)}</div>
            ${detailsHtml}
        `;

        a.addEventListener('click', function(e) {
            e.preventDefault();
            const offcanvas = document.getElementById('sidebarOffcanvas');
            if (offcanvas) {
                const bsOffcanvas = bootstrap.Offcanvas.getInstance(offcanvas);
                if (bsOffcanvas) bsOffcanvas.hide();
            }
            setTimeout(() => {
                if (typeof openStudentSnapshot === 'function') {
                    openStudentSnapshot(item.id, item.class_id);
                }
            }, 350);
        });

        container.appendChild(a);
    });
}

// ============================================================
// FOCUS STUDENTS
// ============================================================
function renderFocusStudents(focusList) {
    const container = document.getElementById('focusStudentsList');
    if (!container) return;

    container.innerHTML = '';

    if (!focusList || focusList.length === 0) {
        container.innerHTML = `
            <div class="focus-empty-state">
                <i class="bi bi-star"></i>
                <span>No focus students</span>
            </div>
        `;
        return;
    }

    focusList.forEach(f => {
        const item = document.createElement('a');
        item.href = '#';
        item.className = 'focus-student-item';
        item.dataset.studentId = f.id;
        item.dataset.classId = f.class_id;

        const reasonHtml = f.reason
            ? `<span class="focus-item-reason">${escapeHtmlSidebar(f.reason)}</span>`
            : '';

        item.innerHTML = `
            <i class="bi bi-star-fill focus-star-icon"></i>
            <div class="focus-item-info">
                <span class="focus-item-name">${escapeHtmlSidebar(f.name)}</span>
                <span class="focus-item-class">${escapeHtmlSidebar(f.class_name)}</span>
                ${reasonHtml}
            </div>
        `;

        item.addEventListener('click', function(e) {
            e.preventDefault();
            const offcanvas = document.getElementById('sidebarOffcanvas');
            if (offcanvas) {
                const bsOffcanvas = bootstrap.Offcanvas.getInstance(offcanvas);
                if (bsOffcanvas) bsOffcanvas.hide();
            }
            setTimeout(() => {
                if (typeof openStudentSnapshot === 'function') {
                    openStudentSnapshot(f.id, f.class_id);
                }
            }, 350);
        });

        container.appendChild(item);
    });
}

// ============================================================
// FOCUS BADGE
// ============================================================
function updateFocusBadge(studentId, classId, isFocused) {
    const row = document.querySelector(`tr[data-student-id="${studentId}"][data-class-id="${classId}"]`);
    if (row) {
        const wrapper = row.querySelector('.student-name-wrapper');
        if (wrapper) {
            let badge = wrapper.querySelector('.focus-badge-star');
            if (isFocused && !badge) {
                badge = document.createElement('span');
                badge.className = 'focus-badge-star';
                badge.title = 'Focus Student';
                badge.innerHTML = '<i class="bi bi-star-fill"></i>';
                wrapper.appendChild(badge);
            } else if (!isFocused && badge) {
                badge.remove();
            }
        }
    }

    const card = document.querySelector(`.student-card-mobile[data-student-id="${studentId}"][data-class-id="${classId}"]`);
    if (card) {
        const wrapper = card.querySelector('.student-name-wrapper');
        if (wrapper) {
            let badge = wrapper.querySelector('.focus-badge-star');
            if (isFocused && !badge) {
                badge = document.createElement('span');
                badge.className = 'focus-badge-star';
                badge.title = 'Focus Student';
                badge.innerHTML = '<i class="bi bi-star-fill"></i>';
                wrapper.appendChild(badge);
            } else if (!isFocused && badge) {
                badge.remove();
            }
        }
    }
}
window.updateFocusBadge = updateFocusBadge;

// --- Render activity log ---
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

// ============================================================
// UPDATE SIDEBAR INFO
// ============================================================
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
        // Stats
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
            backupEl.classList.remove(
                'backup-status-healthy', 'backup-status-warning',
                'backup-status-old', 'backup-status-none', 'backup-status-unknown'
            );
            if (data.last_backup) {
                backupEl.textContent = data.last_backup;
                backupEl.classList.add(`backup-status-${health}`);
            } else {
                backupEl.textContent = 'Never';
                backupEl.classList.add('backup-status-none');
            }
        }

        // Notifications
        const wrapper = document.getElementById('missingAssessmentsWrapper');
        const badge = document.getElementById('notificationBadge');
        const link = document.getElementById('missingAssessmentsLink');
        const dropdown = document.getElementById('pendingClassDropdown');

        if (wrapper && badge && link && dropdown) {
            const count = data.missing_assessments_count || 0;
            badge.textContent = count;

            const oldDropdown = bootstrap.Dropdown.getInstance(link);
            if (oldDropdown) oldDropdown.dispose();
            const oldTip = bootstrap.Tooltip.getInstance(link);
            if (oldTip) oldTip.dispose();

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
                wrapper.style.display = 'block';
                link.classList.add('disabled');
                link.style.pointerEvents = 'none';
                link.style.opacity = '0.6';
                dropdown.innerHTML = '';
            }
        }

        // Needs attention
        renderNeedsAttention(data.needs_attention || []);

        // Focus students
        renderFocusStudents(data.focus_students || []);

        // Recent activity
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
        headers: { 'X-CSRFToken': csrfToken, 'X-Requested-With': 'XMLHttpRequest' },
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'ok') {
            const preview = document.getElementById('profilePicPreview');
            if (preview) preview.innerHTML = `<img src="${data.image_url}" alt="Profile picture">`;
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
    .catch(err => { console.error(err); showNotification('Upload failed.', 'danger'); })
    .finally(() => { input.value = ''; });
}

// --- Profile Picture: Delete ---
function deleteProfilePic() {
    if (!confirm('Remove profile picture?')) return;
    fetch('/profile/delete-picture/', {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken, 'X-Requested-With': 'XMLHttpRequest' }
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'ok') {
            const preview = document.getElementById('profilePicPreview');
            if (preview) {
                preview.innerHTML = `<div class="avatar-placeholder"><i class="bi bi-person-fill"></i></div>`;
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
    .catch(err => { console.error(err); showNotification('Failed to remove picture.', 'danger'); });
}

// --- Restore Database ---
const restoreFileInput = document.getElementById('restoreFileInput');
const restoreDatabaseBtn = document.getElementById('restoreDatabaseBtn');
const confirmRestoreBtn = document.getElementById('confirmRestoreBtn');
let restoreModal;
let selectedRestoreFile = null;

document.addEventListener('DOMContentLoaded', function () {
    const restoreModalEl = document.getElementById('restoreConfirmModal');
    if (restoreModalEl) restoreModal = new bootstrap.Modal(restoreModalEl);
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
        if (!file.name.toLowerCase().endsWith('.sqlite3')) {
            showNotification('Invalid file format. Must be .sqlite3', 'danger');
            restoreFileInput.value = '';
            return;
        }
        selectedRestoreFile = file;
        if (restoreModal) restoreModal.show();
    });
}

if (confirmRestoreBtn) {
    confirmRestoreBtn.addEventListener('click', function () {
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
            headers: { 'X-CSRFToken': csrfToken, 'X-Requested-With': 'XMLHttpRequest' },
            body: formData
        })
        .then(res => {
            if (!res.ok) {
                return res.json().then(data => { throw new Error(data.message || 'Server error ' + res.status); })
                    .catch(() => { throw new Error('Server error ' + res.status); });
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
            showNotification(err.message || 'Network error.', 'danger');
        })
        .finally(() => {
            btn.disabled = false;
            btn.innerHTML = originalHTML;
            if (restoreFileInput) restoreFileInput.value = '';
            selectedRestoreFile = null;
        });
    });
}

document.getElementById('restoreConfirmModal')?.addEventListener('hidden.bs.modal', function () {
    if (restoreFileInput) restoreFileInput.value = '';
    selectedRestoreFile = null;
});

// --- Sidebar events ---
const sidebarEl = document.getElementById('sidebarOffcanvas');
if (sidebarEl) {
    sidebarEl.addEventListener('show.bs.offcanvas', updateSidebarInfo);
    sidebarEl.addEventListener('shown.bs.offcanvas', function () {
        setTimeout(updateSidebarInfo, 100);
    });
    sidebarEl.addEventListener('click', function (e) { e.stopPropagation(); });
    sidebarEl.addEventListener('hide.bs.offcanvas', function (e) {
        const dropdownMenu = document.querySelector('#pendingClassDropdown.show');
        if (dropdownMenu) e.preventDefault();
    });
}

// --- Profile Pic input ---
document.addEventListener('DOMContentLoaded', function () {
    const profilePicInput = document.getElementById('profilePicInput');
    if (profilePicInput) {
        profilePicInput.addEventListener('change', function () { uploadProfilePic(this); });
    }
    const delBtn = document.getElementById('deleteProfilePicBtn');
    if (delBtn) delBtn.addEventListener('click', deleteProfilePic);
});

// --- Backup Database ---
const backupBtn = document.getElementById('backupDatabaseBtn');
if (backupBtn) {
    backupBtn.addEventListener('click', async function () {
        const btn = this;
        const originalHTML = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span><span class="item-label">Backing up...</span>';

        try {
            const infoRes = await fetch('/backup-database/?ajax=true', {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            const info = await infoRes.json();
            if (info.status !== 'ok') throw new Error(info.message || 'Backup failed');

            const downloadLink = document.createElement('a');
            downloadLink.href = '/backup-database/';
            downloadLink.download = info.filename;
            document.body.appendChild(downloadLink);
            downloadLink.click();
            document.body.removeChild(downloadLink);

            addActivityLog('Database backup downloaded');
            showNotification(`Backup saved: ${info.filename}`, 'success');
            if (typeof updateSidebarInfo === 'function') updateSidebarInfo();
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

// --- Fix aria-hidden warning ---
document.addEventListener('hide.bs.modal', function(e) {
    const focused = document.activeElement;
    if (focused && e.target.contains(focused)) {
        focused.blur();
    }
}, true);

// ============================================================
// STUDENT SNAPSHOT — universal modal
// ============================================================
function escapeHtmlSnapshot(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

async function openStudentSnapshot(studentId, classId) {
    const modalEl = document.getElementById('snapshotModal');
    const bodyEl = document.getElementById('snapshotBody');
    if (!modalEl || !bodyEl) return;

    bodyEl.innerHTML = `
        <div class="snapshot-loading">
            <div class="spinner-border" role="status"></div>
            <p>Loading student data...</p>
        </div>
    `;

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();

    const url = `/student/${studentId}/snapshot/` + (classId ? `?class_id=${classId}` : '');

    try {
        const res = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
        const data = await res.json();
        if (data.status !== 'ok') {
            bodyEl.innerHTML = `<div class="alert alert-danger m-3">${escapeHtmlSnapshot(data.message || 'Failed to load.')}</div>`;
            return;
        }
        bodyEl.innerHTML = renderSnapshot(data);
    } catch (err) {
        console.error('Snapshot error:', err);
        bodyEl.innerHTML = `<div class="alert alert-danger m-3">Network error.</div>`;
    }
}

function renderSnapshot(data) {
    const s = data.student;
    const c = data.class;
    const st = data.stats;

    const archivedBadge = c.is_archived ? `<span class="badge snapshot-archived-badge">Archived</span>` : '';
    const inactiveBadge = !s.is_active ? `<span class="badge" style="background: rgba(0,0,0,0.25); color:#fff;">Inactive</span>` : '';

    function pickScoreColorClass(value) {
        if (value === null || value === undefined) return 'muted';
        if (value < 70) return 'red';
        if (value < 80) return 'amber';
        return 'green';
    }
    function pickAttendanceColorClass(pct) {
        if (pct === 0) return 'muted';
        if (pct < 70) return 'red';
        if (pct < 85) return 'amber';
        return 'green';
    }

    const finalScore = st.final_score !== null ? st.final_score : '—';
    const finalCls = pickScoreColorClass(st.final_score);
    const attendanceCls = pickAttendanceColorClass(st.attendance_pct);

    const statsHtml = `
        <div class="snapshot-stats">
            <div class="snapshot-stat">
                <div class="stat-label"><i class="bi bi-plus-circle-fill"></i> Positive</div>
                <div class="stat-value green">+${st.total_positive}</div>
            </div>
            <div class="snapshot-stat">
                <div class="stat-label"><i class="bi bi-dash-circle-fill"></i> Negative</div>
                <div class="stat-value ${st.total_negative > 0 ? 'red' : 'muted'}">-${st.total_negative}</div>
            </div>
            <div class="snapshot-stat">
                <div class="stat-label"><i class="bi bi-wallet2"></i> Avail</div>
                <div class="stat-value avail">${st.available_points}</div>
            </div>
            <div class="snapshot-stat">
                <div class="stat-label"><i class="bi bi-gift-fill"></i> Bonus</div>
                <div class="stat-value ${st.bonus_earned > 0 ? 'gold' : 'muted'}">${st.bonus_earned > 0 ? '+' + st.bonus_earned : '0'}</div>
            </div>
            <div class="snapshot-stat">
                <div class="stat-label"><i class="bi bi-calendar-check"></i> Attendance</div>
                <div class="stat-value ${attendanceCls}">${st.attendance_pct}%</div>
            </div>
            <div class="snapshot-stat">
                <div class="stat-label"><i class="bi bi-trophy-fill"></i> Final</div>
                <div class="stat-value ${finalCls}">${finalScore}</div>
            </div>
        </div>
    `;

    let behaviorHtml = '';
    if (data.recent_behavior.length === 0) {
        behaviorHtml = `<div class="snapshot-empty"><i class="bi bi-clock-history"></i>No recent behavior entries</div>`;
    } else {
        behaviorHtml = '<div class="snapshot-list">';
        data.recent_behavior.forEach(b => {
            const cls = b.points > 0 ? 'positive' : 'negative';
            const sign = b.points > 0 ? '+' : '';
            behaviorHtml += `
                <div class="snapshot-list-item">
                    <span class="snapshot-points-badge ${cls}">${sign}${b.points}</span>
                    <div class="snapshot-list-content">
                        <div class="snapshot-list-note">${escapeHtmlSnapshot(b.note) || '<em class="text-muted">(no note)</em>'}</div>
                        <span class="snapshot-list-time"><i class="bi bi-clock"></i> ${escapeHtmlSnapshot(b.time)}</span>
                    </div>
                </div>
            `;
        });
        behaviorHtml += '</div>';
    }

    let assessmentsHtml = '';
    if (data.recent_assessments.length === 0) {
        assessmentsHtml = `<div class="snapshot-empty"><i class="bi bi-journal-x"></i>No assessments yet</div>`;
    } else {
        assessmentsHtml = '<div class="snapshot-list">';
        data.recent_assessments.forEach(a => {
            let scoreDisplay = '';
            if (a.graded) {
                let cls = 'high';
                if (a.percentage < 70) cls = 'low';
                else if (a.percentage < 80) cls = 'medium';
                scoreDisplay = `<div class="score-value ${cls}">${a.score}/${a.max}</div><div class="score-pct">${a.percentage}%</div>`;
            } else {
                scoreDisplay = `<div class="score-value empty">—</div><div class="score-pct">Not graded</div>`;
            }
            assessmentsHtml += `
                <div class="snapshot-assessment">
                    <div class="snapshot-assessment-info">
                        <div class="snapshot-assessment-name">${escapeHtmlSnapshot(a.name)}</div>
                        <div class="snapshot-assessment-meta">${escapeHtmlSnapshot(a.type)} · ${escapeHtmlSnapshot(a.date)}</div>
                    </div>
                    <div class="snapshot-assessment-score">${scoreDisplay}</div>
                </div>
            `;
        });
        assessmentsHtml += '</div>';
    }

    let noteSection = '';
    if (data.has_private_note) {
        noteSection = `
            <div class="snapshot-section">
                <h6 class="snapshot-section-title"><i class="bi bi-journal-bookmark-fill"></i> Private Note (Teacher-only)</h6>
                <div class="snapshot-note-preview">${escapeHtmlSnapshot(data.private_note)}</div>
            </div>
        `;
    }

    let actionsHtml = '';
    if (!c.is_archived) {
        actionsHtml = `
            <div class="snapshot-actions">
                <a href="/student-feedback/${s.id}/${c.id}/" class="btn btn-feedback"><i class="bi bi-journal-text"></i> Feedback</a>
                <button type="button" class="btn btn-note" data-snapshot-action="note" data-student-id="${s.id}"><i class="bi bi-journal-bookmark-fill"></i> Note</button>
                <a href="/students/${s.id}/history/" class="btn btn-history"><i class="bi bi-clock-history"></i> Full History</a>
            </div>
        `;
    } else {
        actionsHtml = `
            <div class="snapshot-actions">
                <a href="/archive/class/${c.id}/" class="btn btn-history" style="flex: 1 1 100%;"><i class="bi bi-archive-fill"></i> View Archived Class</a>
            </div>
        `;
    }

    const otherEnrollments = data.other_enrollments_count > 0
        ? `<span><i class="bi bi-journal-bookmark-fill"></i> ${data.other_enrollments_count} other class${data.other_enrollments_count === 1 ? '' : 'es'}</span>`
        : '';

    const focusData = data.focus || { is_focused: false, reason: '' };
    let focusHtml = '';

    if (!c.is_archived) {
        if (focusData.is_focused) {
            const reasonText = focusData.reason ? escapeHtmlSnapshot(focusData.reason) : 'No reason set';
            const reasonCls = focusData.reason ? '' : 'empty';
            focusHtml = `
                <div class="snapshot-focus-area">
                    <div class="focus-active-wrap" id="focusActiveWrap">
                        <i class="bi bi-star-fill focus-star"></i>
                        <div class="focus-active-content">
                            <span class="focus-active-label">Focus Student</span>
                            <span class="focus-active-reason ${reasonCls}" id="focusReasonDisplay">${reasonText}</span>
                        </div>
                        <div class="focus-actions">
                            <button type="button" class="btn-focus-icon focus-edit-reason-btn" data-student-id="${s.id}" data-class-id="${c.id}" title="Edit reason"><i class="bi bi-pencil-fill"></i></button>
                            <button type="button" class="btn-focus-icon danger focus-remove-btn" data-student-id="${s.id}" data-class-id="${c.id}" title="Remove from focus"><i class="bi bi-x-lg"></i></button>
                        </div>
                    </div>
                    <div class="focus-reason-editor" id="focusReasonEditor">
                        <label>Focus Reason (optional)</label>
                        <input type="text" class="focus-reason-input" id="focusReasonInput" maxlength="200" placeholder="e.g., Needs motivation, Frequent absences" value="${escapeHtmlSnapshot(focusData.reason || '')}">
                        <div class="focus-reason-actions">
                            <button type="button" class="btn-focus-cancel" id="focusReasonCancelBtn">Cancel</button>
                            <button type="button" class="btn-focus-save" id="focusReasonSaveBtn" data-student-id="${s.id}" data-class-id="${c.id}">Save</button>
                        </div>
                    </div>
                </div>
            `;
        } else {
            focusHtml = `
                <div class="snapshot-focus-area">
                    <button type="button" class="btn-focus-add focus-add-btn" data-student-id="${s.id}" data-class-id="${c.id}">
                        <i class="bi bi-star"></i> Add to Focus
                    </button>
                </div>
            `;
        }
    }

    return `
        <div class="snapshot-header">
            <div class="snapshot-avatar">${escapeHtmlSnapshot(s.initials)}</div>
            <div class="snapshot-header-info">
                <h5 class="snapshot-name">${escapeHtmlSnapshot(s.name)}</h5>
                <div class="snapshot-meta">
                    <span><i class="bi bi-book-fill"></i> ${escapeHtmlSnapshot(c.name)}</span>
                    <span><i class="bi bi-calendar-range"></i> ${escapeHtmlSnapshot(c.semester)}</span>
                    ${otherEnrollments}
                    ${archivedBadge}
                    ${inactiveBadge}
                </div>
                ${focusHtml}
            </div>
        </div>
        <div class="snapshot-section">
            <h6 class="snapshot-section-title"><i class="bi bi-graph-up-arrow"></i> Overview</h6>
            ${statsHtml}
        </div>
        <div class="snapshot-section">
            <h6 class="snapshot-section-title"><i class="bi bi-clock-history"></i> Recent Behavior</h6>
            ${behaviorHtml}
        </div>
        <div class="snapshot-section">
            <h6 class="snapshot-section-title"><i class="bi bi-journal-check"></i> Recent Assessments</h6>
            ${assessmentsHtml}
        </div>
        ${noteSection}
        ${actionsHtml}
    `;
}

// Snapshot trigger
document.addEventListener('click', function(e) {
    const trigger = e.target.closest('.student-snapshot-trigger');
    if (!trigger) return;
    e.preventDefault();
    const studentId = trigger.dataset.studentId;
    const classId = trigger.dataset.classId || '';
    if (!studentId) return;
    openStudentSnapshot(studentId, classId);
});

// Snapshot note action
document.addEventListener('click', function(e) {
    const btn = e.target.closest('[data-snapshot-action="note"]');
    if (!btn) return;
    e.preventDefault();
    const studentId = btn.dataset.studentId;
    if (!studentId) return;
    const snapshotModalEl = document.getElementById('snapshotModal');
    const snapshotInstance = bootstrap.Modal.getInstance(snapshotModalEl);
    if (snapshotInstance) snapshotInstance.hide();
    setTimeout(() => {
        const noteIcon = document.querySelector(`.note-icon[data-student-id="${studentId}"]`);
        if (noteIcon) noteIcon.click();
    }, 350);
});

// Focus: Add
document.addEventListener('click', async function (e) {
    const btn = e.target.closest('.focus-add-btn');
    if (!btn) return;
    e.preventDefault();
    const studentId = btn.dataset.studentId;
    const classId = btn.dataset.classId;
    if (!studentId || !classId) return;

    const originalHTML = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

    try {
        const res = await fetch(`/student/${studentId}/class/${classId}/focus/toggle/`, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrfToken, 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ reason: '' })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            showNotification(data.message, 'success');
            addActivityLog(data.message);
            updateFocusBadge(studentId, classId, data.is_focused);
            updateSidebarInfo();
            openStudentSnapshot(studentId, classId);
        } else {
            showNotification(data.message || 'Failed.', 'danger');
            btn.disabled = false;
            btn.innerHTML = originalHTML;
        }
    } catch (err) {
        console.error('Focus toggle error:', err);
        showNotification('Network error.', 'danger');
        btn.disabled = false;
        btn.innerHTML = originalHTML;
    }
});

// Focus: Remove
document.addEventListener('click', async function (e) {
    const btn = e.target.closest('.focus-remove-btn');
    if (!btn) return;
    e.preventDefault();
    if (!confirm('Remove this student from Focus list?')) return;
    const studentId = btn.dataset.studentId;
    const classId = btn.dataset.classId;
    if (!studentId || !classId) return;

    try {
        const res = await fetch(`/student/${studentId}/class/${classId}/focus/toggle/`, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrfToken, 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({})
        });
        const data = await res.json();
        if (data.status === 'ok') {
            showNotification(data.message, 'success');
            addActivityLog(data.message);
            updateFocusBadge(studentId, classId, data.is_focused);
            updateSidebarInfo();
            openStudentSnapshot(studentId, classId);
        } else {
            showNotification(data.message || 'Failed.', 'danger');
        }
    } catch (err) {
        console.error('Focus remove error:', err);
        showNotification('Network error.', 'danger');
    }
});

// Focus: Edit reason open
document.addEventListener('click', function (e) {
    const btn = e.target.closest('.focus-edit-reason-btn');
    if (!btn) return;
    e.preventDefault();
    const editor = document.getElementById('focusReasonEditor');
    if (editor) {
        editor.classList.toggle('show');
        if (editor.classList.contains('show')) {
            const input = document.getElementById('focusReasonInput');
            if (input) input.focus();
        }
    }
});

// Focus: Cancel
document.addEventListener('click', function (e) {
    const btn = e.target.closest('#focusReasonCancelBtn');
    if (!btn) return;
    e.preventDefault();
    const editor = document.getElementById('focusReasonEditor');
    if (editor) editor.classList.remove('show');
});

// Focus: Save reason
document.addEventListener('click', async function (e) {
    const btn = e.target.closest('#focusReasonSaveBtn');
    if (!btn) return;
    e.preventDefault();
    const studentId = btn.dataset.studentId;
    const classId = btn.dataset.classId;
    const input = document.getElementById('focusReasonInput');
    const reason = input ? input.value.trim() : '';

    const originalHTML = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

    try {
        const res = await fetch(`/student/${studentId}/class/${classId}/focus/reason/`, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrfToken, 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ reason: reason })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            showNotification(data.message, 'success');
            const display = document.getElementById('focusReasonDisplay');
            if (display) {
                if (reason) {
                    display.textContent = reason;
                    display.classList.remove('empty');
                } else {
                    display.textContent = 'No reason set';
                    display.classList.add('empty');
                }
            }
            const editor = document.getElementById('focusReasonEditor');
            if (editor) editor.classList.remove('show');
        } else {
            showNotification(data.message || 'Failed.', 'danger');
        }
    } catch (err) {
        console.error('Focus reason save error:', err);
        showNotification('Network error.', 'danger');
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalHTML;
    }
});