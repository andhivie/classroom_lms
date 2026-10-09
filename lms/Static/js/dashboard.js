// ========== CSRF TOKEN ==========
function getCsrfToken() {
    if (typeof csrfToken !== 'undefined' && csrfToken && csrfToken.length > 20) {
        return csrfToken;
    }
    const name = 'csrftoken';
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) {
        const token = parts.pop().split(';').shift();
        if (token && token.length > 20) return token;
    }
    const hiddenInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (hiddenInput) return hiddenInput.value;
    return '';
}
const CSRF_TOKEN = getCsrfToken();

// ========== BASIC UTILITIES ==========
function showNotification(message, type) {
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
}

const bulkAddMessage = sessionStorage.getItem('bulkAddMessage');
if (bulkAddMessage) {
    try { const msg = JSON.parse(bulkAddMessage); showNotification(msg.text, msg.type); } catch (e) {}
    sessionStorage.removeItem('bulkAddMessage');
}
const assessmentMessage = sessionStorage.getItem('assessmentMessage');
if (assessmentMessage) {
    try { const msg = JSON.parse(assessmentMessage); showNotification(msg.text, msg.type); } catch (e) {}
    sessionStorage.removeItem('assessmentMessage');
}

// ========== RANDOMIZER HELPERS ==========
function getStudentNamesFromClass(classId) {
    const rows = document.querySelectorAll(`tr[data-class-id="${classId}"]`);
    const names = [];
    rows.forEach(row => {
        const nameSpan = row.querySelector('.student-name-container span');
        if (nameSpan) { const name = nameSpan.innerText.trim(); if (name) names.push(name); }
    });
    return names;
}
function escapeHtml(str) {
    return str.replace(/[&<>]/g, function(m) {
        if (m === '&') return '&amp;'; if (m === '<') return '&lt;'; if (m === '>') return '&gt;'; return m;
    });
}

// ========== TEAM GENERATOR ==========
let teamHistory = [];
function loadTeamHistory() {
    const stored = localStorage.getItem('teamGeneratorHistoryFull');
    if (stored) { try { teamHistory = JSON.parse(stored); } catch(e) { teamHistory = []; } }
    renderTeamHistory();
}
function saveTeamHistory() { localStorage.setItem('teamGeneratorHistoryFull', JSON.stringify(teamHistory)); }
function addTeamHistory(classId, teamCount, teamsArray) {
    const timestamp = new Date().toLocaleString();
    const classSelect = document.getElementById('teamClassSelect');
    const className = classSelect.options[classSelect.selectedIndex]?.text || classId;
    teamHistory.unshift({ classId, className, teamCount, teams: teamsArray, timestamp });
    if (teamHistory.length > 20) teamHistory.pop();
    saveTeamHistory(); renderTeamHistory();
}
function renderTeamHistory() {
    const list = document.getElementById('teamHistoryList');
    if (!list) return;
    if (teamHistory.length === 0) { list.innerHTML = '<li class="list-group-item text-muted">No history yet.</li>'; return; }
    list.innerHTML = '';
    teamHistory.forEach((item) => {
        const li = document.createElement('li');
        li.className = 'list-group-item history-clickable';
        li.innerHTML = `<strong>${item.timestamp}</strong><br>Class: ${item.className}, Teams: ${item.teamCount}<br><small class="text-primary">Click for details</small>`;
        li.addEventListener('click', () => showTeamDetail(item));
        list.appendChild(li);
    });
}
function showTeamDetail(item) {
    document.getElementById('historyDetailTitle').textContent = `Team Detail - ${item.className} (${item.timestamp})`;
    let html = `<p><strong>Teams:</strong> ${item.teamCount}</p>`;
    item.teams.forEach((team, idx) => {
        const teamLetter = String.fromCharCode(65 + idx);
        html += `<p><strong>Team ${teamLetter}</strong><br>${team.map(m => `• ${escapeHtml(m)}`).join('<br>')}</p>`;
    });
    document.getElementById('historyDetailBody').innerHTML = html;
    new bootstrap.Modal(document.getElementById('historyDetailModal')).show();
}
document.getElementById('showTeamHistoryBtn')?.addEventListener('click', () => {
    const panel = document.getElementById('teamHistoryPanel');
    panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
});
document.getElementById('clearTeamHistoryBtn')?.addEventListener('click', () => {
    teamHistory = []; saveTeamHistory(); renderTeamHistory(); showNotification('Team history cleared.', 'success');
});
document.getElementById('generateTeamsBtn')?.addEventListener('click', function() {
    const classId = document.getElementById('teamClassSelect').value;
    const teamCount = parseInt(document.getElementById('teamCount').value, 10);
    if (!classId) { showNotification('Select a class first.', 'warning'); return; }
    let names = getStudentNamesFromClass(classId);
    if (names.length === 0) { showNotification('No students in this class.', 'warning'); return; }
    for (let i = names.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [names[i], names[j]] = [names[j], names[i]];
    }
    const teams = Array.from({ length: teamCount }, () => []);
    names.forEach((name, idx) => { teams[idx % teamCount].push(name); });
    const container = document.getElementById('teamsContainer');
    container.innerHTML = '';
    teams.forEach((team, idx) => {
        const col = document.createElement('div');
        col.className = 'col-md-4 col-sm-6 mb-3';
        const teamLetter = String.fromCharCode(65 + idx);
        const teamMembers = team.map(n => `<li class="list-group-item">${escapeHtml(n)}</li>`).join('');
        col.innerHTML = `<div class="card h-100 shadow-sm team-card"><div class="card-header text-white">Team ${teamLetter} (${team.length} members)</div><div class="card-body p-0"><ul class="list-group list-group-flush">${teamMembers}</ul></div></div>`;
        container.appendChild(col);
    });
    addTeamHistory(classId, teamCount, teams);
});

// ========== PAIR GENERATOR ==========
let pairHistory = [];
function loadPairHistory() {
    const stored = localStorage.getItem('pairGeneratorHistoryFull');
    if (stored) { try { pairHistory = JSON.parse(stored); } catch(e) { pairHistory = []; } }
    renderPairHistory();
}
function savePairHistory() { localStorage.setItem('pairGeneratorHistoryFull', JSON.stringify(pairHistory)); }
function addPairHistory(classId, pairsArray) {
    const timestamp = new Date().toLocaleString();
    const classSelect = document.getElementById('pairClassSelect');
    const className = classSelect.options[classSelect.selectedIndex]?.text || classId;
    pairHistory.unshift({ classId, className, pairs: pairsArray, timestamp });
    if (pairHistory.length > 20) pairHistory.pop();
    savePairHistory(); renderPairHistory();
}
function renderPairHistory() {
    const list = document.getElementById('pairHistoryList');
    if (!list) return;
    if (pairHistory.length === 0) { list.innerHTML = '<li class="list-group-item text-muted">No history yet.</li>'; return; }
    list.innerHTML = '';
    pairHistory.forEach((item) => {
        const li = document.createElement('li');
        li.className = 'list-group-item history-clickable';
        li.innerHTML = `<strong>${item.timestamp}</strong><br>Class: ${item.className}, Pairs: ${item.pairs.length}<br><small class="text-primary">Click for details</small>`;
        li.addEventListener('click', () => showPairDetail(item));
        list.appendChild(li);
    });
}
function showPairDetail(item) {
    document.getElementById('historyDetailTitle').textContent = `Pair Detail - ${item.className} (${item.timestamp})`;
    let html = `<p><strong>Pairs:</strong> ${item.pairs.length}</p><ol>`;
    item.pairs.forEach((pair, idx) => {
        const partner = pair[1] ? pair[1] : '(alone)';
        html += `<li><strong>${idx+1}.</strong> ${escapeHtml(pair[0])} & ${escapeHtml(partner)}</li>`;
    });
    html += '</ol>';
    document.getElementById('historyDetailBody').innerHTML = html;
    new bootstrap.Modal(document.getElementById('historyDetailModal')).show();
}
document.getElementById('showPairHistoryBtn')?.addEventListener('click', () => {
    const panel = document.getElementById('pairHistoryPanel');
    panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
});
document.getElementById('clearPairHistoryBtn')?.addEventListener('click', () => {
    pairHistory = []; savePairHistory(); renderPairHistory();
    document.getElementById('pairsResult').style.display = 'none';
    document.getElementById('pairsTableBody').innerHTML = '';
    showNotification('Pair history cleared.', 'success');
});
document.getElementById('generatePairsBtn')?.addEventListener('click', function() {
    const classId = document.getElementById('pairClassSelect').value;
    if (!classId) { showNotification('Select a class first.', 'warning'); return; }
    let names = getStudentNamesFromClass(classId);
    if (names.length === 0) { showNotification('No students in this class.', 'warning'); return; }
    for (let i = names.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [names[i], names[j]] = [names[j], names[i]];
    }
    const pairs = [];
    for (let i = 0; i < names.length; i += 2) pairs.push([names[i], names[i+1] || '']);
    const tbody = document.getElementById('pairsTableBody');
    tbody.innerHTML = '';
    pairs.forEach((pair, idx) => {
        const row = tbody.insertRow();
        row.insertCell(0).innerText = idx + 1;
        row.insertCell(1).innerText = pair[0];
        row.insertCell(2).innerText = pair[1] || '(solo)';
    });
    document.getElementById('pairsResult').style.display = 'block';
    addPairHistory(classId, pairs);
});
document.getElementById('pairClassSelect')?.addEventListener('change', function() {
    document.getElementById('pairsResult').style.display = 'none';
    document.getElementById('pairsTableBody').innerHTML = '';
});

// ========== NAME RANDOMIZER ==========
let nameHistoryMap = {};
function loadNameHistory(classId) {
    const stored = localStorage.getItem(`nameHistory_${classId}`);
    if (stored) nameHistoryMap[classId] = JSON.parse(stored); else nameHistoryMap[classId] = [];
}
function saveNameHistory(classId) { localStorage.setItem(`nameHistory_${classId}`, JSON.stringify(nameHistoryMap[classId] || [])); }
function resetNameHistory(classId) { nameHistoryMap[classId] = []; saveNameHistory(classId); }
function getRemainingNamesForClass(classId) {
    const names = getStudentNamesFromClass(classId);
    const used = nameHistoryMap[classId] || [];
    return names.filter((_, idx) => !used.includes(idx));
}
function markNameUsed(classId, name) {
    const names = getStudentNamesFromClass(classId);
    const idx = names.findIndex(n => n === name);
    if (idx !== -1 && !(nameHistoryMap[classId] || []).includes(idx)) {
        if (!nameHistoryMap[classId]) nameHistoryMap[classId] = [];
        nameHistoryMap[classId].push(idx); saveNameHistory(classId);
    }
}
function spinWheelAnimation(finalName, callback) {
    const wheelDiv = document.getElementById('wheelResult');
    const spinIcon = document.getElementById('spinAnimation');
    spinIcon.style.display = 'block'; wheelDiv.style.opacity = '0.5';
    let counter = 0;
    const fakeNames = ['✨', '🌟', '⭐', '💫', '⚡', '🎲', '🔁'];
    const interval = setInterval(() => { wheelDiv.innerHTML = `<span style="font-size:1.5rem;">${fakeNames[counter % fakeNames.length]}</span>`; counter++; }, 100);
    setTimeout(() => {
        clearInterval(interval); spinIcon.style.display = 'none'; wheelDiv.style.opacity = '1';
        wheelDiv.innerHTML = `<span class="fw-bold">${escapeHtml(finalName)}</span>`;
        if (callback) callback();
    }, 800);
}
document.getElementById('spinWheelBtn')?.addEventListener('click', function() {
    const classId = document.getElementById('nameClassSelect').value;
    if (!classId) { showNotification('Select a class first.', 'warning'); return; }
    loadNameHistory(classId);
    let remaining = getRemainingNamesForClass(classId);
    if (remaining.length === 0) { resetNameHistory(classId); remaining = getRemainingNamesForClass(classId); if (remaining.length === 0) { showNotification('No students in this class.', 'warning'); return; } }
    const chosen = remaining[Math.floor(Math.random() * remaining.length)];
    spinWheelAnimation(chosen, () => { markNameUsed(classId, chosen); });
});
document.getElementById('resetNameHistoryBtn')?.addEventListener('click', function() {
    const classId = document.getElementById('nameClassSelect').value;
    if (!classId) { showNotification('Select a class first.', 'warning'); return; }
    resetNameHistory(classId); showNotification('Name history reset.', 'success');
    document.getElementById('wheelResult').innerHTML = '<span class="fw-bold">🎲 Ready</span>';
});
// ---------- Randomizer modal: auto-select current class ----------
document.getElementById('randomizerModal')?.addEventListener('show.bs.modal', function() {
    loadTeamHistory();
    loadPairHistory();

    // Determine current class — prefer dashboard dropdown (always in sync),
    // fall back to URL, then localStorage.
    let currentClassId = '';

    const dashSelect = document.getElementById('class_select');
    if (dashSelect && dashSelect.value) {
        currentClassId = dashSelect.value;
    } else {
        const urlParams = new URLSearchParams(window.location.search);
        currentClassId = urlParams.get('class_id') || '';
    }

    // If still empty, try localStorage
    if (!currentClassId) {
        currentClassId = localStorage.getItem('selectedClassId') || '';
    }

    if (currentClassId) {
        const selects = ['teamClassSelect', 'nameClassSelect', 'pairClassSelect', 'seatClassSelect'];
        selects.forEach(id => {
            const selectEl = document.getElementById(id);
            if (!selectEl) return;

            // Always override to match current dashboard class
            const option = Array.from(selectEl.options).find(opt => opt.value === currentClassId);
            if (option) {
                selectEl.value = currentClassId;
            }
        });
    }
});

// ========== SEAT RANDOMIZER ==========
let currentSeatLayout = 'rows';
let currentSeatNames = [];

document.querySelectorAll('.seat-layout-btn').forEach(btn => {
    btn.addEventListener('click', function() {
        document.querySelectorAll('.seat-layout-btn').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        currentSeatLayout = this.dataset.layout;
        if (currentSeatNames.length > 0) {
            renderSeatPlan(currentSeatNames, currentSeatLayout, parseInt(document.getElementById('seatColumns').value) || 4);
        }
    });
});

let dragSrcIndex = null;

function renderSeatPlan(names, layout, columns) {
    const container = document.getElementById('seatPlanContainer');
    const total = names.length;
    if (total === 0) {
        container.innerHTML = '<div class="text-center text-muted py-4 small">No students</div>';
        return;
    }
    container.innerHTML = '';
    if (layout === 'rows') {
        const rows = Math.ceil(total / columns);
        const plan = document.createElement('div'); plan.className = 'seat-plan';
        for (let r = 0; r < rows; r++) {
            const rowDiv = document.createElement('div'); rowDiv.className = 'seat-row';
            for (let c = 0; c < columns; c++) {
                const idx = r * columns + c;
                const desk = createDeskElement(names, idx, total);
                rowDiv.appendChild(desk);
            }
            plan.appendChild(rowDiv);
        }
        container.appendChild(plan);
    } else if (layout === 'clusters') {
        const clusterSize = 4; const numClusters = Math.ceil(total / clusterSize);
        const perRow = Math.min(numClusters, columns);
        const plan = document.createElement('div'); plan.className = 'seat-plan'; let ni = 0;
        for (let cr = 0; cr < Math.ceil(numClusters / perRow); cr++) {
            const rowDiv = document.createElement('div'); rowDiv.className = 'seat-row';
            for (let cc = 0; cc < perRow; cc++) {
                if (ni >= total) break;
                const clusterDiv = document.createElement('div'); clusterDiv.className = 'seat-cluster';
                for (let i = 0; i < 4; i++) {
                    const desk = createDeskElement(names, ni, total);
                    clusterDiv.appendChild(desk); ni++;
                }
                rowDiv.appendChild(clusterDiv);
            }
            plan.appendChild(rowDiv);
        }
        container.appendChild(plan);
    } else if (layout === 'pairs') {
        const numPairs = Math.ceil(total / 2); const perRow = columns;
        const plan = document.createElement('div'); plan.className = 'seat-plan'; let ni = 0;
        for (let pr = 0; pr < Math.ceil(numPairs / perRow); pr++) {
            const rowDiv = document.createElement('div'); rowDiv.className = 'seat-row';
            for (let pc = 0; pc < perRow; pc++) {
                if (ni >= total) break;
                const pairDiv = document.createElement('div'); pairDiv.className = 'seat-pair';
                for (let i = 0; i < 2; i++) {
                    const desk = createDeskElement(names, ni, total);
                    pairDiv.appendChild(desk); ni++;
                }
                rowDiv.appendChild(pairDiv);
            }
            plan.appendChild(rowDiv);
        }
        container.appendChild(plan);
    } else if (layout === 'ushape') {
        const half = Math.ceil(total / 2);
        const top = names.slice(0, half); const bottom = names.slice(half);
        const ushape = document.createElement('div'); ushape.className = 'seat-ushape';
        const topDiv = document.createElement('div'); topDiv.className = 'seat-row';
        top.forEach((n, i) => { const d = createDeskElement(names, i, total); topDiv.appendChild(d); });
        ushape.appendChild(topDiv);
        const botDiv = document.createElement('div'); botDiv.className = 'seat-row';
        bottom.reverse().forEach((n, i) => { const d = createDeskElement(names, half + bottom.length - 1 - i, total); botDiv.appendChild(d); });
        ushape.appendChild(botDiv);
        container.appendChild(ushape);
    }
}

function createDeskElement(names, idx, total) {
    const desk = document.createElement('div');
    desk.className = 'seat-desk';
    desk.textContent = idx < total ? names[idx] : '—';
    if (idx >= total) {
        desk.classList.add('empty-seat');
    } else {
        desk.setAttribute('draggable', 'true');
        desk.dataset.index = idx;
        desk.addEventListener('dragstart', handleDragStart);
        desk.addEventListener('dragover', handleDragOver);
        desk.addEventListener('drop', handleDrop);
        desk.addEventListener('dragend', handleDragEnd);
    }
    return desk;
}

function handleDragStart(e) {
    if (this.classList.contains('empty-seat')) { e.preventDefault(); return; }
    dragSrcIndex = parseInt(this.dataset.index);
    this.style.opacity = '0.4';
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', this.textContent);
}
function handleDragOver(e) { if (e.preventDefault) e.preventDefault(); e.dataTransfer.dropEffect = 'move'; return false; }
function handleDrop(e) {
    e.stopPropagation(); e.preventDefault();
    if (!this.classList.contains('empty-seat') && this.dataset.index !== undefined) {
        const targetIndex = parseInt(this.dataset.index);
        if (!isNaN(dragSrcIndex) && !isNaN(targetIndex) && dragSrcIndex !== targetIndex) {
            [currentSeatNames[dragSrcIndex], currentSeatNames[targetIndex]] = [currentSeatNames[targetIndex], currentSeatNames[dragSrcIndex]];
            const columns = parseInt(document.getElementById('seatColumns').value) || 4;
            renderSeatPlan(currentSeatNames, currentSeatLayout, columns);
        }
    }
    return false;
}
function handleDragEnd(e) { this.style.opacity = '1'; dragSrcIndex = null; }

document.getElementById('generateSeatBtn')?.addEventListener('click', function() {
    const classId = document.getElementById('seatClassSelect').value;
    const columns = parseInt(document.getElementById('seatColumns').value, 10) || 4;
    if (!classId) { showNotification('Select a class first.', 'warning'); return; }
    let names = getStudentNamesFromClass(classId);
    if (names.length === 0) { showNotification('No students.', 'warning'); return; }
    names = names.map(n => {
        const parts = n.trim().split(/\s+/);
        if (parts.length === 1) return parts[0];
        if (parts.length === 2) return parts[1];
        return parts[1];
    });
    for (let i = names.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [names[i], names[j]] = [names[j], names[i]];
    }
    currentSeatNames = [...names];
    renderSeatPlan(currentSeatNames, currentSeatLayout, columns);
});

document.getElementById('resetSeatBtn')?.addEventListener('click', function() {
    if (currentSeatNames.length === 0) return;
    const columns = parseInt(document.getElementById('seatColumns').value, 10) || 4;
    renderSeatPlan(currentSeatNames, currentSeatLayout, columns);
});

// ========== RESET POINTS MODAL ==========
let resetPointsContext = null;

function showResetPointsModal() {
    if (!resetPointsContext) return;
    const title = document.getElementById('resetPointsModalTitle');
    const message = document.getElementById('resetPointsModalMessage');
    const checkbox = document.getElementById('fullResetCheckbox');

    checkbox.checked = false;

    if (resetPointsContext.type === 'student') {
        title.innerHTML = '<i class="bi bi-arrow-counterclockwise me-2"></i>Reset Behavior Points';
        message.innerHTML = `Reset behavior points for <strong>${resetPointsContext.studentName}</strong>?`;
    } else {
        title.innerHTML = '<i class="bi bi-arrow-counterclockwise me-2"></i>Reset Class Points';
        message.innerHTML = `Reset behavior points for <strong>ALL students</strong> in <strong>${resetPointsContext.className}</strong>?`;
    }

    new bootstrap.Modal(document.getElementById('resetPointsModal')).show();
}

document.getElementById('confirmResetPointsBtn')?.addEventListener('click', function() {
    if (!resetPointsContext) return;
    const fullReset = document.getElementById('fullResetCheckbox').checked;
    const btn = this;
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Resetting...';

    const formData = new URLSearchParams();
    formData.append('full_reset', fullReset ? 'true' : 'false');

    let url;
    if (resetPointsContext.type === 'student') {
        url = `/reset-student-points/${resetPointsContext.studentId}/${resetPointsContext.classId}/`;
    } else {
        url = `/reset-class-points/${resetPointsContext.classId}/`;
    }

    fetch(url, {
        method: 'POST',
        headers: {
            'X-CSRFToken': CSRF_TOKEN,
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded'
        },
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'ok') {
            showNotification(data.message, 'success');
            if (typeof addActivityLog === 'function') addActivityLog(data.message);
            bootstrap.Modal.getInstance(document.getElementById('resetPointsModal')).hide();
            setTimeout(() => window.location.reload(), 800);
        } else {
            showNotification(data.message || 'Failed', 'danger');
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    })
    .catch(err => {
        console.error(err);
        showNotification('Network error', 'danger');
        btn.disabled = false;
        btn.innerHTML = originalText;
    });
});

// ========== AJAX HANDLERS ==========
function attachAjaxEvents() {
    // Behavior buttons
    document.querySelectorAll('.ajax-behavior').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const studentId = this.dataset.studentId;
            const classId = this.dataset.classId;
            const points = this.dataset.points;
            const btnElem = this;

            btnElem.disabled = true;
            btnElem.style.opacity = '0.6';
            btnElem.blur();

            const formData = new URLSearchParams();
            formData.append('points', points);

            fetch(`/add-behavior/${studentId}/${classId}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': CSRF_TOKEN,
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/x-www-form-urlencoded'
                },
                body: formData
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'ok') {
                    updateStudentUI(studentId, classId, data);
                    showNotification(data.message, 'success');
                    if (typeof addActivityLog === 'function') {
                        addActivityLog(`Behavior point ${points > 0 ? '+' + points : points} added`);
                    }
                    if (typeof updateSidebarInfo === 'function') updateSidebarInfo();
                } else {
                    showNotification(data.message || 'Failed', 'danger');
                }
            })
            .catch(err => { console.error(err); showNotification('Network error', 'danger'); })
            .finally(() => {
                btnElem.disabled = false;
                btnElem.style.opacity = '1';
                btnElem.blur();
            });
        });
    });

    // --- Edit student ---
    document.querySelectorAll('.edit-student-icon').forEach(icon => {
        icon.addEventListener('click', function (e) {
            e.preventDefault();
            const studentId = this.dataset.studentId;
            const studentName = this.dataset.studentName;
            const studentEmail = this.dataset.studentEmail || '';

            document.getElementById('editStudentId').value = studentId;
            document.getElementById('editStudentName').value = studentName;
            document.getElementById('editStudentEmail').value = studentEmail;

            const modalEl = document.getElementById('editStudentModal');
            if (modalEl) new bootstrap.Modal(modalEl).show();
        });
    });

    // --- Edit student form submit ---
    const editStudentForm = document.getElementById('editStudentForm');
    if (editStudentForm && !editStudentForm.dataset.bound) {
        editStudentForm.dataset.bound = 'true';
        editStudentForm.addEventListener('submit', async function (e) {
            e.preventDefault();

            const studentId = document.getElementById('editStudentId').value;
            const newName = document.getElementById('editStudentName').value.trim();
            const newEmail = document.getElementById('editStudentEmail').value.trim();

            if (!newName) {
                showNotification('Name cannot be empty.', 'warning');
                return;
            }

            const submitBtn = editStudentForm.querySelector('button[type="submit"]');
            const originalHTML = submitBtn.innerHTML;
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Saving...';

            const formData = new URLSearchParams();
            formData.append('name', newName);
            formData.append('email', newEmail);

            try {
                const res = await fetch(`/edit-student/${studentId}/`, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': CSRF_TOKEN,
                        'X-Requested-With': 'XMLHttpRequest',
                        'Content-Type': 'application/x-www-form-urlencoded'
                    },
                    body: formData
                });
                const data = await res.json();

                if (data.status === 'ok') {
                    showNotification(data.message, 'success');
                    if (typeof addActivityLog === 'function') addActivityLog('Student info updated');

                    // Update UI: find all rows/cards with this student and update name
                    document.querySelectorAll(`[data-student-id="${studentId}"]`).forEach(el => {
                        // Desktop table name span
                        const nameSpan = el.querySelector('.student-name-container > span');
                        if (nameSpan) nameSpan.textContent = newName;
                        // Mobile card name
                        const mobileName = el.querySelector('.mobile-name');
                        if (mobileName) mobileName.textContent = newName;
                        // Update data-student-name on the delete icon + reset icon + convert button
                        el.querySelectorAll('[data-student-name]').forEach(node => {
                            node.dataset.studentName = newName;
                        });
                        // Update title attribute for the edit icon
                        const editIcon = el.querySelector('.edit-student-icon');
                        if (editIcon) {
                            editIcon.dataset.studentName = newName;
                            editIcon.dataset.studentEmail = newEmail;
                        }
                    });

                    // Close modal
                    const modalEl = document.getElementById('editStudentModal');
                    const modalInstance = bootstrap.Modal.getInstance(modalEl);
                    if (modalInstance) modalInstance.hide();
                } else {
                    showNotification(data.message || 'Failed to save.', 'danger');
                }
            } catch (err) {
                console.error('Edit student error:', err);
                showNotification('Network error.', 'danger');
            } finally {
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalHTML;
            }
        });
    }

    // ============================================================
    // PRIVATE NOTES — event delegation
    // ============================================================

    let noteAutosaveTimer = null;
    let noteCurrentStudentId = null;

    // ---------- Open note modal ----------
    document.addEventListener('click', function (e) {
        const icon = e.target.closest('.note-icon');
        if (!icon) return;
        e.preventDefault();

        const studentId = icon.dataset.studentId;
        const studentName = icon.dataset.studentName;

        noteCurrentStudentId = studentId;

        document.getElementById('noteStudentId').value = studentId;
        document.getElementById('noteStudentName').textContent = studentName;
        document.getElementById('noteTextarea').value = '';
        document.getElementById('noteMetaInfo').textContent = 'Loading...';
        document.getElementById('deleteNoteBtn').style.display = 'none';
        document.getElementById('noteAutosaveIndicator').classList.remove('show');

        const modalEl = document.getElementById('noteModal');
        if (modalEl) {
            bootstrap.Modal.getOrCreateInstance(modalEl).show();
        }

        // Fetch existing note
        fetch(`/student/${studentId}/note/`, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'ok') {
                    document.getElementById('noteTextarea').value = data.note || '';

                    if (data.has_note) {
                        document.getElementById('noteMetaInfo').innerHTML =
                            `<i class="bi bi-clock-history me-1"></i>Last updated: ${data.updated_at}`;
                        document.getElementById('deleteNoteBtn').style.display = 'inline-flex';
                    } else {
                        document.getElementById('noteMetaInfo').textContent = 'No note yet. Start typing to add one.';
                    }
                } else {
                    document.getElementById('noteMetaInfo').textContent = 'Failed to load note.';
                }
            })
            .catch(err => {
                console.error('Note load error:', err);
                document.getElementById('noteMetaInfo').textContent = 'Network error.';
            });
    });

    // ---------- Auto-save on typing (debounced) ----------
    document.addEventListener('input', function (e) {
        if (!e.target.matches('#noteTextarea')) return;

        clearTimeout(noteAutosaveTimer);
        noteAutosaveTimer = setTimeout(() => {
            performNoteAutosave();
        }, 2000);
    });

    function performNoteAutosave() {
        const studentId = document.getElementById('noteStudentId').value;
        const noteText = document.getElementById('noteTextarea').value;

        // Skip autosave if textarea is empty AND there's no existing note
        if (!noteText.trim()) {
            return;
        }

        const formData = new URLSearchParams();
        formData.append('note', noteText);
        formData.append('action', 'save');

        fetch(`/student/${studentId}/note/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': CSRF_TOKEN,
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: formData
        })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'ok') {
                    document.getElementById('noteMetaInfo').innerHTML =
                        `<i class="bi bi-clock-history me-1"></i>Last updated: ${data.updated_at}`;
                    document.getElementById('deleteNoteBtn').style.display = 'inline-flex';

                    const indicator = document.getElementById('noteAutosaveIndicator');
                    indicator.classList.add('show');
                    setTimeout(() => indicator.classList.remove('show'), 2000);

                    // Update icon visual state
                    updateNoteIconState(studentId, true);
                }
            })
            .catch(err => console.error('Autosave error:', err));
    }

    // ---------- Manual save ----------
    document.addEventListener('click', function (e) {
        const btn = e.target.closest('#saveNoteBtn');
        if (!btn) return;
        e.preventDefault();

        const studentId = document.getElementById('noteStudentId').value;
        const noteText = document.getElementById('noteTextarea').value;

        const originalHTML = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Saving...';

        const formData = new URLSearchParams();
        formData.append('note', noteText);
        formData.append('action', noteText.trim() ? 'save' : 'delete');

        fetch(`/student/${studentId}/note/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': CSRF_TOKEN,
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: formData
        })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'ok') {
                    showNotification(data.message, 'success');
                    if (typeof addActivityLog === 'function') addActivityLog('Private note saved');

                    const hasNote = data.has_note;

                    if (hasNote) {
                        document.getElementById('noteMetaInfo').innerHTML =
                            `<i class="bi bi-clock-history me-1"></i>Last updated: ${data.updated_at}`;
                        document.getElementById('deleteNoteBtn').style.display = 'inline-flex';
                    } else {
                        document.getElementById('noteMetaInfo').textContent = 'No note yet. Start typing to add one.';
                        document.getElementById('deleteNoteBtn').style.display = 'none';
                    }

                    updateNoteIconState(studentId, hasNote);

                    const modalEl = document.getElementById('noteModal');
                    const modalInstance = bootstrap.Modal.getInstance(modalEl);
                    if (modalInstance) modalInstance.hide();
                } else {
                    showNotification(data.message || 'Failed to save note.', 'danger');
                }
            })
            .catch(err => {
                console.error('Save note error:', err);
                showNotification('Network error.', 'danger');
            })
            .finally(() => {
                btn.disabled = false;
                btn.innerHTML = originalHTML;
            });
    });

    // ---------- Delete note ----------
    document.addEventListener('click', function (e) {
        const btn = e.target.closest('#deleteNoteBtn');
        if (!btn) return;
        e.preventDefault();

        if (!confirm('Delete this note permanently?')) return;

        const studentId = document.getElementById('noteStudentId').value;

        const formData = new URLSearchParams();
        formData.append('action', 'delete');

        fetch(`/student/${studentId}/note/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': CSRF_TOKEN,
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: formData
        })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'ok') {
                    showNotification(data.message, 'success');
                    if (typeof addActivityLog === 'function') addActivityLog('Private note deleted');

                    document.getElementById('noteTextarea').value = '';
                    document.getElementById('noteMetaInfo').textContent = 'No note yet. Start typing to add one.';
                    document.getElementById('deleteNoteBtn').style.display = 'none';

                    updateNoteIconState(studentId, false);

                    const modalEl = document.getElementById('noteModal');
                    const modalInstance = bootstrap.Modal.getInstance(modalEl);
                    if (modalInstance) modalInstance.hide();
                } else {
                    showNotification(data.message || 'Failed to delete note.', 'danger');
                }
            })
            .catch(err => {
                console.error('Delete note error:', err);
                showNotification('Network error.', 'danger');
            });
    });

    // ---------- Helper: update note icon visual state ----------
    function updateNoteIconState(studentId, hasNote) {
        document.querySelectorAll(`.note-icon[data-student-id="${studentId}"]`).forEach(icon => {
            const i = icon.querySelector('i');
            if (!i) return;

            if (hasNote) {
                icon.classList.remove('no-note');
                icon.classList.add('has-note');
                i.className = 'bi bi-journal-bookmark-fill';
                icon.title = 'Private note (has content)';
            } else {
                icon.classList.remove('has-note');
                icon.classList.add('no-note');
                i.className = 'bi bi-journal-bookmark';
                icon.title = 'Add private note';
            }
        });
    }

    // Reset student points — open modal
    document.querySelectorAll('.ajax-reset-student-points').forEach(icon => {
        icon.addEventListener('click', function(e) {
            e.preventDefault();
            resetPointsContext = {
                type: 'student',
                studentId: this.dataset.studentId,
                classId: this.dataset.classId,
                studentName: this.dataset.studentName,
            };
            showResetPointsModal();
        });
    });

    // Reset class points — open modal
    document.querySelectorAll('.ajax-reset-class-points').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            resetPointsContext = {
                type: 'class',
                classId: this.dataset.classId,
                className: this.dataset.className,
            };
            showResetPointsModal();
        });
    });

    // Convert bonus
    document.querySelectorAll('.ajax-convert-bonus').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            if (this.disabled) return;
            const studentId = this.dataset.studentId;
            const classId = this.dataset.classId;
            const studentName = this.dataset.studentName;
            const btnElem = this;

            if (!confirm(`Convert available points into academic bonus for ${studentName}?`)) return;

            btnElem.disabled = true;
            btnElem.style.opacity = '0.6';
            btnElem.blur();

            fetch(`/convert-bonus/${studentId}/${classId}/`, {
                method: 'POST',
                headers: { 'X-CSRFToken': CSRF_TOKEN, 'X-Requested-With': 'XMLHttpRequest' }
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'ok') {
                    showNotification(data.message, 'success');
                    if (typeof addActivityLog === 'function') addActivityLog(`Bonus converted for ${studentName}`);
                    setTimeout(() => window.location.reload(), 800);
                } else {
                    showNotification(data.message || 'Conversion failed.', 'danger');
                    btnElem.disabled = false;
                    btnElem.style.opacity = '1';
                }
            })
            .catch(err => {
                console.error(err);
                showNotification('Network error', 'danger');
                btnElem.disabled = false;
                btnElem.style.opacity = '1';
            });
        });
    });

    // Delete student
    document.querySelectorAll('.ajax-delete-student').forEach(icon => {
        icon.addEventListener('click', function(e) {
            e.preventDefault();
            const studentId = this.dataset.studentId;
            const classId = this.dataset.classId;
            const studentName = this.dataset.studentName;
            if (!confirm(`Remove ${studentName} from this class?`)) return;
            const elem = this; elem.style.opacity = '0.6'; elem.blur();
            fetch(`/delete-student/${studentId}/${classId}/`, {
                method: 'POST',
                headers: { 'X-CSRFToken': CSRF_TOKEN, 'X-Requested-With': 'XMLHttpRequest' }
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'ok') {
                    const row = document.querySelector(`tr[data-student-id="${studentId}"][data-class-id="${classId}"]`);
                    if (row) row.remove();
                    const card = document.querySelector(`.student-card-mobile[data-student-id="${studentId}"][data-class-id="${classId}"]`);
                    if (card) card.remove();
                    showNotification(data.message, 'success');
                    if (typeof addActivityLog === 'function') addActivityLog(`Student removed: ${studentName}`);
                    if (typeof updateSidebarInfo === 'function') updateSidebarInfo();
                } else {
                    showNotification(data.message || 'Failed', 'danger');
                }
            })
            .catch(err => { console.error(err); showNotification('Network error', 'danger'); })
            .finally(() => { elem.style.opacity = '1'; elem.blur(); });
        });
    });

    // Delete class
    document.querySelectorAll('.ajax-delete-class').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const classId = this.dataset.classId;
            const className = this.dataset.className;
            if (!confirm(`Delete entire class "${className}"? All data will be lost.`)) return;
            const btnElem = this;
            btnElem.disabled = true;
            btnElem.style.opacity = '0.6';
            fetch(`/delete-class/${classId}/`, { method: 'POST', headers: { 'X-CSRFToken': CSRF_TOKEN, 'X-Requested-With': 'XMLHttpRequest' } })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'ok') {
                    showNotification(data.message, 'success');
                    if (typeof addActivityLog === 'function') addActivityLog(`Class deleted: ${className}`);
                    setTimeout(() => window.location.reload(), 1000);
                } else {
                    showNotification(data.message || 'Failed', 'danger');
                    btnElem.disabled = false;
                    btnElem.style.opacity = '1';
                }
            })
            .catch(err => {
                console.error(err);
                showNotification('Network error', 'danger');
                btnElem.disabled = false;
                btnElem.style.opacity = '1';
            });
        });
    });
}

function updateStudentUI(studentId, classId, data) {
    const row = document.querySelector(`tr[data-student-id="${studentId}"][data-class-id="${classId}"]`);
    if (row) {
        const summaryCell = row.querySelector('.behavior-summary-col');
        if (summaryCell) summaryCell.innerHTML = buildSummaryHTML(data);

        const finalCell = row.querySelector('.final-score-cell');
        if (finalCell) {
            if (data.new_final_score !== undefined && data.new_final_score !== null) {
                finalCell.innerHTML = `<span class="${data.new_final_score < 80 ? 'text-danger' : 'text-dark'}">${data.new_final_score}</span>`;
            } else {
                finalCell.innerHTML = '<span class="text-muted">-</span>';
            }
        }

        const convertBtn = row.querySelector('.ajax-convert-bonus');
        if (convertBtn) {
            convertBtn.disabled = !data.can_convert;
            convertBtn.title = data.can_convert ? 'Convert points into bonus' : (data.conversion_error || '');
        }
    }

    const card = document.querySelector(`.student-card-mobile[data-student-id="${studentId}"][data-class-id="${classId}"]`);
    if (card) {
        const metaRow = card.querySelector('.mobile-meta-row');
        if (metaRow) {
            const attText = metaRow.querySelector('.meta-att')?.outerHTML || '';
            const finalText = metaRow.querySelector('.meta-final')?.outerHTML || '';

            let html = `
                <span class="meta-summary">
                    <span class="text-success fw-semibold">+${data.total_positive}</span><span class="text-muted">/</span><span class="text-danger fw-semibold">-${data.total_negative}</span>
                </span>
                <span class="meta-avail"><strong>Avail: ${data.available_points}</strong></span>
            `;
            if (data.daily_test_status === 'ready') {
                html += `<span class="badge bg-success">✓</span>`;
            } else if (data.daily_test_status === 'not_ready') {
                html += `<span class="badge bg-secondary">-${data.points_needed_for_test}</span>`;
            }
            if (data.bonus_earned > 0) {
                html += `<span class="badge bg-warning text-dark">+${data.bonus_earned}b</span>`;
            }
            html += `<span class="meta-sep">·</span>`;
            html += attText;
            html += `<span class="meta-sep">·</span>`;
            if (data.new_final_score !== undefined && data.new_final_score !== null) {
                html += `<span class="meta-final"><span class="${data.new_final_score < 80 ? 'text-danger' : 'text-success'} fw-semibold">Final: ${data.new_final_score}</span></span>`;
            } else {
                html += `<span class="meta-final"><span class="text-muted">Final: -</span></span>`;
            }
            metaRow.innerHTML = html;
        }

        const mobileConvertBtn = card.querySelector('.ajax-convert-bonus');
        if (mobileConvertBtn) {
            mobileConvertBtn.disabled = !data.can_convert;
            if (data.can_convert) {
                mobileConvertBtn.title = 'Convert points into bonus';
            } else {
                mobileConvertBtn.title = data.conversion_error || '';
            }
        }
    }
}

function buildSummaryHTML(data) {
    let html = `
        <span class="summary-points">
            <span class="text-success fw-semibold">+${data.total_positive}</span><span class="text-muted">/</span><span class="text-danger fw-semibold">-${data.total_negative}</span>
        </span>
        <span class="summary-divider">·</span>
        <span class="summary-avail"><strong>Avail: ${data.available_points}</strong></span>
    `;
    if (data.daily_test_status === 'ready') {
        html += `<span class="badge bg-success" title="Ready for Daily Test">✓</span>`;
    } else if (data.daily_test_status === 'not_ready') {
        html += `<span class="badge bg-secondary" title="Need ${data.points_needed_for_test} more">-${data.points_needed_for_test}</span>`;
    }
    if (data.bonus_earned > 0) {
        html += `<span class="badge bg-warning text-dark" title="Bonus earned">+${data.bonus_earned}b</span>`;
    }
    return `<div class="summary-row">${html}</div>`;
}

document.addEventListener('DOMContentLoaded', function() {
    attachAjaxEvents();
    startHighlightRotation();

    // ============================================================
    // EVENT DELEGATION — robust for AJAX-rendered content
    // ============================================================

    // ---------- One-Click Praise: open modal ----------
    document.addEventListener('click', function (e) {
        const btn = e.target.closest('.btn-praise-icon');
        if (!btn) return;
        e.preventDefault();

        const studentId = btn.dataset.studentId;
        const classId = btn.dataset.classId;
        const studentName = btn.dataset.studentName;

        document.getElementById('praiseStudentId').value = studentId;
        document.getElementById('praiseClassId').value = classId;
        document.getElementById('praiseStudentName').textContent = studentName;
        document.getElementById('praiseCustomNote').value = '';

        document.querySelectorAll('#praisePresetChips .praise-preset-chip').forEach(c => c.classList.remove('selected'));
        document.querySelectorAll('.praise-point-btn').forEach(b => {
            b.classList.toggle('selected', b.dataset.points === '3');
        });

        const modalEl = document.getElementById('praiseModal');
        if (modalEl) {
            bootstrap.Modal.getOrCreateInstance(modalEl).show();
        }
    });

    // ---------- Edit Student: open modal ----------
    document.addEventListener('click', function (e) {
        const icon = e.target.closest('.edit-student-icon');
        if (!icon) return;
        e.preventDefault();

        const studentId = icon.dataset.studentId;
        const studentName = icon.dataset.studentName;
        const studentEmail = icon.dataset.studentEmail || '';

        document.getElementById('editStudentId').value = studentId;
        document.getElementById('editStudentName').value = studentName;
        document.getElementById('editStudentEmail').value = studentEmail;

        const modalEl = document.getElementById('editStudentModal');
        if (modalEl) {
            bootstrap.Modal.getOrCreateInstance(modalEl).show();
        }
    });

    // ---------- Praise: preset chip selection ----------
    document.addEventListener('click', function (e) {
        const chip = e.target.closest('#praisePresetChips .praise-preset-chip');
        if (!chip) return;

        const isSelected = chip.classList.contains('selected');
        document.querySelectorAll('#praisePresetChips .praise-preset-chip').forEach(c => c.classList.remove('selected'));
        if (!isSelected) {
            chip.classList.add('selected');
            document.getElementById('praiseCustomNote').value = '';
        }
    });

    // ---------- Praise: points selector ----------
    document.addEventListener('click', function (e) {
        const pbtn = e.target.closest('.praise-point-btn');
        if (!pbtn) return;

        document.querySelectorAll('.praise-point-btn').forEach(b => b.classList.remove('selected'));
        pbtn.classList.add('selected');
    });

    // ---------- Praise: clear chip selection on custom note typing ----------
    document.addEventListener('input', function (e) {
        if (!e.target.matches('#praiseCustomNote')) return;
        if (e.target.value.trim().length > 0) {
            document.querySelectorAll('#praisePresetChips .praise-preset-chip').forEach(c => c.classList.remove('selected'));
        }
    });

    // ---------- Praise: form submit ----------
    document.addEventListener('submit', async function (e) {
        const form = e.target.closest('#praiseForm');
        if (!form) return;
        e.preventDefault();

        const studentId = document.getElementById('praiseStudentId').value;
        const classId = document.getElementById('praiseClassId').value;

        let note = '';
        const selectedChip = document.querySelector('#praisePresetChips .praise-preset-chip.selected');
        if (selectedChip) {
            note = selectedChip.dataset.note;
        } else {
            note = document.getElementById('praiseCustomNote').value.trim();
        }

        if (!note) {
            showNotification('Please select a reason or write a note.', 'warning');
            return;
        }

        const selectedPointBtn = document.querySelector('.praise-point-btn.selected');
        const points = selectedPointBtn ? selectedPointBtn.dataset.points : '3';

        const btn = document.getElementById('savePraiseBtn');
        const originalHTML = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Sending...';

        const formData = new URLSearchParams();
        formData.append('points', points);
        formData.append('note', note);

        try {
            const res = await fetch(`/add-behavior/${studentId}/${classId}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': CSRF_TOKEN,
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/x-www-form-urlencoded'
                },
                body: formData
            });
            const data = await res.json();

            if (data.status === 'ok') {
                updateStudentUI(studentId, classId, data);
                showNotification(`⭐ Praised ${document.getElementById('praiseStudentName').textContent} (+${points})`, 'success');
                if (typeof addActivityLog === 'function') {
                    addActivityLog(`Praise: ${note} (+${points})`);
                }
                if (typeof updateSidebarInfo === 'function') updateSidebarInfo();

                const modalEl = document.getElementById('praiseModal');
                const modalInstance = bootstrap.Modal.getInstance(modalEl);
                if (modalInstance) modalInstance.hide();
            } else {
                showNotification(data.message || 'Failed to send praise.', 'danger');
            }
        } catch (err) {
            console.error('Praise error:', err);
            showNotification('Network error.', 'danger');
        } finally {
            btn.disabled = false;
            btn.innerHTML = originalHTML;
        }
    });

    // ---------- Edit Student: form submit ----------
    document.addEventListener('submit', async function (e) {
        const form = e.target.closest('#editStudentForm');
        if (!form) return;
        e.preventDefault();

        const studentId = document.getElementById('editStudentId').value;
        const newName = document.getElementById('editStudentName').value.trim();
        const newEmail = document.getElementById('editStudentEmail').value.trim();

        if (!newName) {
            showNotification('Name cannot be empty.', 'warning');
            return;
        }

        const submitBtn = form.querySelector('button[type="submit"]');
        const originalHTML = submitBtn.innerHTML;
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Saving...';

        const formData = new URLSearchParams();
        formData.append('name', newName);
        formData.append('email', newEmail);

        try {
            const res = await fetch(`/edit-student/${studentId}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': CSRF_TOKEN,
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/x-www-form-urlencoded'
                },
                body: formData
            });
            const data = await res.json();

            if (data.status === 'ok') {
                showNotification(data.message, 'success');
                if (typeof addActivityLog === 'function') addActivityLog('Student info updated');

                document.querySelectorAll(`[data-student-id="${studentId}"]`).forEach(el => {
                    const nameSpan = el.querySelector('.student-name-container > span');
                    if (nameSpan) nameSpan.textContent = newName;
                    const mobileName = el.querySelector('.mobile-name');
                    if (mobileName) mobileName.textContent = newName;
                    el.querySelectorAll('[data-student-name]').forEach(node => {
                        node.dataset.studentName = newName;
                    });
                    const editIcon = el.querySelector('.edit-student-icon');
                    if (editIcon) {
                        editIcon.dataset.studentName = newName;
                        editIcon.dataset.studentEmail = newEmail;
                    }
                });

                const modalEl = document.getElementById('editStudentModal');
                const modalInstance = bootstrap.Modal.getInstance(modalEl);
                if (modalInstance) modalInstance.hide();
            } else {
                showNotification(data.message || 'Failed to save.', 'danger');
            }
        } catch (err) {
            console.error('Edit student error:', err);
            showNotification('Network error.', 'danger');
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalHTML;
        }
    });
});

// ========== LIVE SEARCH & CLASS FILTER ==========
(function() {
    const searchInput = document.getElementById('searchInput');
    let classSelect = document.getElementById('class_select');
    const dashboardContent = document.getElementById('dashboard-content');
    let debounceTimer;
    let isLoading = false;

    function getCurrentClassIdFromUrl() {
        const params = new URLSearchParams(window.location.search);
        return params.get('class_id') || '';
    }

    async function loadDashboardContent(options = {}) {
        if (isLoading) return;
        if (!dashboardContent) return;

        const classId = options.classId !== undefined ? options.classId : getCurrentClassIdFromUrl();
        const searchQuery = options.searchQuery !== undefined ? options.searchQuery : (searchInput ? searchInput.value.trim() : '');

        const url = new URL(window.location.origin + DASHBOARD_URL);
        if (searchQuery) url.searchParams.set('search', searchQuery);
        if (classId) url.searchParams.set('class_id', classId);
        url.searchParams.set('partial', 'true');

        isLoading = true;
        if (classSelect) classSelect.disabled = true;

        try {
            const response = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
            if (!response.ok) throw new Error('Network error');
            const html = await response.text();
            dashboardContent.innerHTML = html;
            if (typeof startHighlightRotation === 'function') {
                startHighlightRotation();
            }

            classSelect = document.getElementById('class_select');

            if (classSelect) {
                if (classId && classSelect.value !== classId) classSelect.value = classId;
                else if (!classId && classSelect.value !== '') classSelect.value = '';
                attachClassSelectListener(classSelect);
            }

            if (classId) localStorage.setItem('selectedClassId', classId);
            else localStorage.removeItem('selectedClassId');

            const newUrl = new URL(window.location);
            if (searchQuery) newUrl.searchParams.set('search', searchQuery);
            else newUrl.searchParams.delete('search');
            if (classId) newUrl.searchParams.set('class_id', classId);
            else newUrl.searchParams.delete('class_id');
            history.pushState(null, '', newUrl);

            if (typeof attachAjaxEvents === 'function') attachAjaxEvents();
            if (typeof updateSidebarInfo === 'function') updateSidebarInfo();

            // Only re-focus the search box if the user is actively typing in it.
            // Otherwise (e.g. after class change) don't focus — prevents mobile keyboard popup.
            if (options.focusSearch && searchInput) {
                searchInput.focus();
                searchInput.setSelectionRange(searchInput.value.length, searchInput.value.length);
            } else if (searchInput) {
                searchInput.blur();
            }
        } catch (err) {
            console.error('Dashboard load error:', err);
            if (typeof showNotification === 'function') showNotification('Failed to load data.', 'danger');
        } finally {
            isLoading = false;
            if (classSelect) classSelect.disabled = false;
        }
    }

    function handleClassChange(e) {
        const newClassId = e.target.value;
        const currentSearch = searchInput ? searchInput.value.trim() : '';
        // Blur search input to avoid mobile keyboard popup
        if (searchInput) searchInput.blur();
        // Defer slightly so the browser closes the native select first
        setTimeout(() => {
            loadDashboardContent({
                classId: newClassId,
                searchQuery: currentSearch,
                focusSearch: false
            });
        }, 50);
    }

    function attachClassSelectListener(selectEl) {
        if (!selectEl) return;
        selectEl.removeEventListener('change', handleClassChange);
        selectEl.addEventListener('change', handleClassChange);
    }

    if (searchInput) {
        searchInput.addEventListener('input', function() {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                const currentClassId = getCurrentClassIdFromUrl();
                loadDashboardContent({
                    classId: currentClassId,
                    searchQuery: searchInput.value.trim(),
                    focusSearch: true
                });
            }, 300);
        });
    }

    if (classSelect) attachClassSelectListener(classSelect);

    window.addEventListener('popstate', function() {
        const params = new URLSearchParams(window.location.search);
        const classId = params.get('class_id') || '';
        const searchQuery = params.get('search') || '';
        if (searchInput) searchInput.value = searchQuery;
        loadDashboardContent({ classId, searchQuery, focusSearch: false });
    });

    const homeLink = document.getElementById('dashboardHomeLink');
    if (homeLink) {
        homeLink.addEventListener('click', function(e) {
            e.preventDefault();
            const classId = localStorage.getItem('selectedClassId');
            let url = DASHBOARD_URL;
            if (classId) url += '?class_id=' + classId;
            window.location.href = url;
        });
    }

    const urlParams = new URLSearchParams(window.location.search);
    const urlClassId = urlParams.get('class_id');
    const storedClassId = localStorage.getItem('selectedClassId');

    if (!urlClassId && storedClassId) {
        let newUrl = DASHBOARD_URL + '?class_id=' + storedClassId;
        const searchQuery = urlParams.get('search');
        if (searchQuery) newUrl += '&search=' + encodeURIComponent(searchQuery);
        window.location.replace(newUrl);
        return;
    }

    if (urlClassId) {
        localStorage.setItem('selectedClassId', urlClassId);
        if (classSelect && classSelect.value !== urlClassId) classSelect.value = urlClassId;
    }
})();

// ========== HIGHLIGHT ROTATION (dynamic, class-aware) ==========
let highlightItems = [];
let highlightIndex = 0;
let highlightInterval = null;

function buildHighlightItems() {
    const dataEl = document.getElementById('highlight-data');
    if (!dataEl) return [];

    const items = [];

    if (dataEl.dataset.hasHp === '1') {
        items.push({
            category: 'positive',
            icon: 'bi-star-fill',
            label: 'Most Positive',
            value: `${dataEl.dataset.hpName} (+${dataEl.dataset.hpPoints})`
        });
    }

    if (dataEl.dataset.hasHn === '1') {
        items.push({
            category: 'negative',
            icon: 'bi-exclamation-triangle-fill',
            label: 'Most Negative',
            value: `${dataEl.dataset.hnName} (-${dataEl.dataset.hnPoints})`
        });
    }

    if (dataEl.dataset.hasHf === '1') {
        items.push({
            category: 'final',
            icon: 'bi-trophy-fill',
            label: 'Highest Final Score',
            value: `${dataEl.dataset.hfName} (${dataEl.dataset.hfScore})`
        });
    }

    return items;
}

function renderHighlightItem(item) {
    const box = document.getElementById('highlightBox');
    const iconEl = document.getElementById('highlightIcon');
    const labelEl = document.getElementById('highlightLabel');
    const valueEl = document.getElementById('highlightText');
    const content = box ? box.querySelector('.highlight-content') : null;

    if (!box || !iconEl || !labelEl || !valueEl || !content) return;

    // Fade out
    content.classList.add('fade-out');

    setTimeout(() => {
        // Update content
        box.dataset.category = item.category;
        iconEl.className = `bi ${item.icon} highlight-icon`;
        labelEl.textContent = item.label;
        valueEl.textContent = item.value;

        // Fade in
        content.classList.remove('fade-out');
        content.classList.add('fade-in');
    }, 280);
}

function startHighlightRotation() {
    // Clear any existing interval
    if (highlightInterval) {
        clearInterval(highlightInterval);
        highlightInterval = null;
    }

    highlightItems = buildHighlightItems();

    const box = document.getElementById('highlightBox');
    const iconEl = document.getElementById('highlightIcon');
    const labelEl = document.getElementById('highlightLabel');
    const valueEl = document.getElementById('highlightText');
    const content = box ? box.querySelector('.highlight-content') : null;

    if (!box || !iconEl || !labelEl || !valueEl || !content) return;

    if (highlightItems.length === 0) {
        box.dataset.category = 'neutral';
        iconEl.className = 'bi bi-stars highlight-icon';
        labelEl.textContent = 'Welcome';
        valueEl.textContent = 'No activity yet';
        return;
    }

    // Show first item immediately
    highlightIndex = 0;
    const first = highlightItems[0];
    box.dataset.category = first.category;
    iconEl.className = `bi ${first.icon} highlight-icon`;
    labelEl.textContent = first.label;
    valueEl.textContent = first.value;

    // Only rotate if more than 1 item
    if (highlightItems.length > 1) {
        highlightInterval = setInterval(() => {
            highlightIndex = (highlightIndex + 1) % highlightItems.length;
            renderHighlightItem(highlightItems[highlightIndex]);
        }, 4500);
    }
}

// ========== RESET CLASS MODAL ==========
let currentResetClassId = null, currentResetBtn = null, currentResetBtnOriginalText = '';
document.addEventListener('click', function(e) {
    const btn = e.target.closest('.open-reset-class-modal');
    if (btn) {
        currentResetClassId = btn.dataset.classId;
        currentResetBtn = btn;
        currentResetBtnOriginalText = btn.innerHTML;
        document.getElementById('deleteStudentsCheckbox').checked = false;
        new bootstrap.Modal(document.getElementById('resetClassModal')).show();
    }
});
document.getElementById('confirmResetClassBtn')?.addEventListener('click', function(e) {
    const deleteStudents = document.getElementById('deleteStudentsCheckbox').checked;
    const confirmBtn = e.target;
    confirmBtn.disabled = true;
    confirmBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Resetting...';
    if (currentResetBtn) {
        currentResetBtn.disabled = true;
        currentResetBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Resetting...';
        currentResetBtn.style.opacity = '1';
    }
    const formData = new URLSearchParams();
    formData.append('delete_students', deleteStudents);

    fetch(`/reset-class-data/${currentResetClassId}/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': CSRF_TOKEN,
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded'
        },
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'ok') {
            showNotification(data.message, 'success');
            if (typeof addActivityLog === 'function') addActivityLog(`Class data reset: ${currentResetBtn?.dataset.className || 'Unknown'}`);
            bootstrap.Modal.getInstance(document.getElementById('resetClassModal')).hide();
            setTimeout(() => window.location.reload(), 1500);
        } else {
            showNotification(data.message || 'Failed', 'danger');
            confirmBtn.disabled = false;
            confirmBtn.innerHTML = 'Reset Class';
            if (currentResetBtn) {
                currentResetBtn.disabled = false;
                currentResetBtn.innerHTML = currentResetBtnOriginalText;
                currentResetBtn.style.opacity = '1';
            }
        }
    })
    .catch(err => {
        console.error(err);
        showNotification('Network error', 'danger');
    });
});