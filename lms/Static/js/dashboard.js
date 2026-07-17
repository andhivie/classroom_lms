// ========== AMBIL CSRF TOKEN DENGAN AMAN ==========
function getCsrfToken() {
    // Coba ambil dari global (dideklarasikan di sidebar.js)
    if (typeof csrfToken !== 'undefined' && csrfToken && csrfToken.length > 20) {
        return csrfToken;
    }
    // Fallback: ambil dari cookie
    const name = 'csrftoken';
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) {
        const token = parts.pop().split(';').shift();
        if (token && token.length > 20) return token;
    }
    // Fallback terakhir: ambil dari elemen hidden (jika ada)
    const hiddenInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (hiddenInput) return hiddenInput.value;
    return '';
}
const CSRF_TOKEN = getCsrfToken();

// ========== FUNGSI DASAR ==========
function updateClock() {
    const now = new Date();
    const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' };
    const clockEl = document.getElementById('live-clock');
    if (clockEl) clockEl.innerText = now.toLocaleDateString('id-ID', options);
}
updateClock();
setInterval(updateClock, 1000);

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

// Pesan dari sessionStorage
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
if (localStorage.getItem('teamGeneratorHistory')) localStorage.removeItem('teamGeneratorHistory');
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
        li.innerHTML = `<strong>${item.timestamp}</strong><br>Kelas: ${item.className}, Tim: ${item.teamCount}<br><small class="text-primary">👆 Click for details</small>`;
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
        col.innerHTML = `<div class="card h-100 shadow-sm"><div class="card-header text-white py-1,2 px-1" style="background-color: #003f5c; font-size: 1rem; text-align: center;">Team ${teamLetter} (${team.length} members)</div><div class="card-body"><ul class="list-group list-group-flush">${teamMembers}</ul></div></div>`;
        container.appendChild(col);
    });
    addTeamHistory(classId, teamCount, teams);
});

// ========== PAIR GENERATOR ==========
let pairHistory = [];
if (localStorage.getItem('pairGeneratorHistory')) localStorage.removeItem('pairGeneratorHistory');
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
        li.innerHTML = `<strong>${item.timestamp}</strong><br>Kelas: ${item.className}, Pasangan: ${item.pairs.length}<br><small class="text-primary">👆 Click for details</small>`;
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

// Name Randomizer
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
document.getElementById('randomizerModal')?.addEventListener('show.bs.modal', function() { loadTeamHistory(); loadPairHistory(); });

// ========== SEAT RANDOMIZER (Drag & Drop) ==========
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

document.getElementById('generateSeatBtn').addEventListener('click', function() {
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

document.getElementById('resetSeatBtn').addEventListener('click', function() {
    if (currentSeatNames.length === 0) return;
    const columns = parseInt(document.getElementById('seatColumns').value, 10) || 4;
    renderSeatPlan(currentSeatNames, currentSeatLayout, columns);
});

// ========== FUNGSI UNTUK MELEKATKAN EVENT LISTENER AJAX ==========
function attachAjaxEvents() {
    document.querySelectorAll('.ajax-behavior').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const studentId = this.dataset.studentId, classId = this.dataset.classId, points = this.dataset.points;
            const btnElem = this;
            btnElem.disabled = true; btnElem.style.opacity = '0.6'; btnElem.blur();
            const formData = new URLSearchParams(); formData.append('points', points);
            fetch(`/add-behavior/${studentId}/${classId}/`, {
                method: 'POST',
                headers: { 'X-CSRFToken': CSRF_TOKEN, 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/x-www-form-urlencoded' },
                body: formData
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'ok') {
                    const row = document.querySelector(`tr[data-student-id="${studentId}"][data-class-id="${classId}"]`);
                    if (row) {
                        const summaryCell = row.querySelector('.behavior-summary-col');
                        if (summaryCell && data.new_summary) summaryCell.innerHTML = data.new_summary;
                        const finalCell = row.querySelector('.final-score-cell');
                        if (finalCell && data.new_final_score !== undefined) {
                            if (data.new_final_score !== null) {
                                finalCell.innerHTML = `<span class="${data.new_final_score < 80 ? 'text-danger' : 'text-dark'}">${data.new_final_score}</span>`;
                            } else { finalCell.innerHTML = '<span class="text-muted">-</span>'; }
                        }
                    }
                    showNotification(data.message, 'success');
                    if (typeof addActivityLog === 'function') addActivityLog(`Behavior point ${points > 0 ? '+' + points : points} added`);
                    // Refresh sidebar info (termasuk badge pending)
                    if (typeof updateSidebarInfo === 'function') updateSidebarInfo();
                } else { showNotification(data.message || 'Failed', 'danger'); }
            })
            .catch(err => { console.error(err); showNotification('Network error', 'danger'); })
            .finally(() => { btnElem.disabled = false; btnElem.style.opacity = '1'; btnElem.blur(); });
        });
    });

    document.querySelectorAll('.ajax-reset-student-points').forEach(icon => {
        icon.addEventListener('click', function(e) {
            e.preventDefault();
            const studentId = this.dataset.studentId, classId = this.dataset.classId, studentName = this.dataset.studentName;
            if (!confirm(`Reset behavior points for ${studentName}?`)) return;
            const elem = this; elem.style.opacity = '0.6'; elem.blur();
            fetch(`/reset-student-points/${studentId}/${classId}/`, {
                method: 'POST', headers: { 'X-CSRFToken': CSRF_TOKEN, 'X-Requested-With': 'XMLHttpRequest' }
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'ok') {
                    const row = document.querySelector(`tr[data-student-id="${studentId}"][data-class-id="${classId}"]`);
                    if (row && data.new_summary) row.querySelector('.behavior-summary-col').innerHTML = data.new_summary;
                    if (row && data.new_final_score !== undefined) {
                        const finalCell = row.querySelector('.final-score-cell');
                        if (data.new_final_score !== null) {
                            finalCell.innerHTML = `<span class="${data.new_final_score < 80 ? 'text-danger' : 'text-dark'}">${data.new_final_score}</span>`;
                        } else { finalCell.innerHTML = '<span class="text-muted">-</span>'; }
                    }
                    showNotification(data.message, 'success');
                    if (typeof addActivityLog === 'function') addActivityLog(`Behavior points reset for ${studentName}`);
                    if (typeof updateSidebarInfo === 'function') updateSidebarInfo();
                } else { showNotification(data.message || 'Failed', 'danger'); }
            })
            .catch(err => { console.error(err); showNotification('Network error', 'danger'); })
            .finally(() => { elem.style.opacity = '1'; elem.blur(); });
        });
    });

    document.querySelectorAll('.ajax-delete-student').forEach(icon => {
        icon.addEventListener('click', function(e) {
            e.preventDefault();
            const studentId = this.dataset.studentId, classId = this.dataset.classId, studentName = this.dataset.studentName;
            if (!confirm(`Remove ${studentName} from this class?`)) return;
            const elem = this; elem.style.opacity = '0.6'; elem.blur();
            fetch(`/delete-student/${studentId}/${classId}/`, {
                method: 'POST', headers: { 'X-CSRFToken': CSRF_TOKEN, 'X-Requested-With': 'XMLHttpRequest' }
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'ok') {
                    const row = document.querySelector(`tr[data-student-id="${studentId}"][data-class-id="${classId}"]`);
                    if (row) row.remove();
                    showNotification(data.message, 'success'); 
                    if (typeof addActivityLog === 'function') addActivityLog(`Student removed: ${studentName}`);
                    if (typeof updateSidebarInfo === 'function') updateSidebarInfo();
                } else { showNotification(data.message || 'Failed', 'danger'); }
            })
            .catch(err => { console.error(err); showNotification('Network error', 'danger'); })
            .finally(() => { elem.style.opacity = '1'; elem.blur(); });
        });
    });

    document.querySelectorAll('.ajax-reset-class-points').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const classId = this.dataset.classId, className = this.dataset.className;
            if (!confirm(`Reset behavior points for ALL students in ${className}? This cannot be undone.`)) return;
            const btnElem = this; const originalText = btnElem.innerHTML;
            btnElem.disabled = true; btnElem.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Resetting...'; btnElem.style.opacity = '1';
            fetch(`/reset-class-points/${classId}/`, {
                method: 'POST', headers: { 'X-CSRFToken': CSRF_TOKEN, 'X-Requested-With': 'XMLHttpRequest' }
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'ok') { showNotification(data.message, 'success'); if (typeof addActivityLog === 'function') addActivityLog(`All behavior points reset for class ${className}`); setTimeout(() => window.location.reload(), 1500); }
                else { showNotification(data.message || 'Failed', 'danger'); btnElem.disabled = false; btnElem.innerHTML = originalText; btnElem.style.opacity = '1'; }
            })
            .catch(err => { console.error(err); showNotification('Network error', 'danger'); btnElem.disabled = false; btnElem.innerHTML = originalText; btnElem.style.opacity = '1'; });
        });
    });

    document.querySelectorAll('.ajax-delete-class').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const classId = this.dataset.classId, className = this.dataset.className;
            if (!confirm(`Delete entire class "${className}"? All data will be lost.`)) return;
            const btnElem = this; btnElem.disabled = true; btnElem.style.opacity = '0.6';
            fetch(`/delete-class/${classId}/`, { method: 'POST', headers: { 'X-CSRFToken': CSRF_TOKEN, 'X-Requested-With': 'XMLHttpRequest' } })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'ok') { showNotification(data.message, 'success'); if (typeof addActivityLog === 'function') addActivityLog(`Class deleted: ${className}`); setTimeout(() => window.location.reload(), 1000); }
                else { showNotification(data.message || 'Failed', 'danger'); btnElem.disabled = false; btnElem.style.opacity = '1'; }
            })
            .catch(err => { console.error(err); showNotification('Network error', 'danger'); btnElem.disabled = false; btnElem.style.opacity = '1'; });
        });
    });
}

// Panggil attachAjaxEvents setelah konten dimuat (juga dipanggil setelah load dashboard via AJAX)
document.addEventListener('DOMContentLoaded', function() {
    attachAjaxEvents();
    
    // Listener untuk Generate Parent Code (delegasi)
    document.addEventListener('click', async function(e) {
        const btn = e.target.closest('.generate-code-btn');
        if (!btn) return;
        e.preventDefault();
        const studentId = btn.dataset.studentId;
        const originalHTML = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
        try {
            const response = await fetch(`/generate-parent-code/${studentId}/`, {
                method: 'POST',
                headers: { 'X-CSRFToken': CSRF_TOKEN, 'X-Requested-With': 'XMLHttpRequest' }
            });
            const data = await response.json();
            if (data.status === 'ok') {
                await navigator.clipboard.writeText(data.code);
                showNotification(`✅ Parent Code: ${data.code} (Copied)`, 'success');
                if (typeof addActivityLog === 'function') addActivityLog('Parent code generated');
            } else {
                showNotification('❌ ' + (data.message || 'Failed to load the code.'), 'danger');
            }
        } catch (err) {
            console.error(err);
            showNotification('❌ Failed to load the code.', 'danger');
        } finally {
            btn.disabled = false;
            btn.innerHTML = originalHTML;
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

        // Gunakan DASHBOARD_URL yang didefinisikan di template
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

            classSelect = document.getElementById('class_select');
            
            if (classSelect) {
                if (classId && classSelect.value !== classId) {
                    classSelect.value = classId;
                } else if (!classId && classSelect.value !== '') {
                    classSelect.value = '';
                }
                attachClassSelectListener(classSelect);
            }

            if (classId) {
                localStorage.setItem('selectedClassId', classId);
            } else {
                localStorage.removeItem('selectedClassId');
            }

            const newUrl = new URL(window.location);
            if (searchQuery) newUrl.searchParams.set('search', searchQuery);
            else newUrl.searchParams.delete('search');
            if (classId) newUrl.searchParams.set('class_id', classId);
            else newUrl.searchParams.delete('class_id');
            history.pushState(null, '', newUrl);

            if (typeof attachAjaxEvents === 'function') {
                attachAjaxEvents();
            }

            // Refresh sidebar info setelah konten dashboard diperbarui
            if (typeof updateSidebarInfo === 'function') {
                updateSidebarInfo();
            }

            if (searchInput) {
                searchInput.focus();
                searchInput.setSelectionRange(searchInput.value.length, searchInput.value.length);
            }
        } catch (err) {
            console.error('Dashboard load error:', err);
            if (typeof showNotification === 'function') {
                showNotification('Gagal memuat data.', 'danger');
            }
        } finally {
            isLoading = false;
            if (classSelect) classSelect.disabled = false;
        }
    }

    function handleClassChange(e) {
        const newClassId = e.target.value;
        const currentSearch = searchInput ? searchInput.value.trim() : '';
        loadDashboardContent({ classId: newClassId, searchQuery: currentSearch });
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
                loadDashboardContent({ classId: currentClassId, searchQuery: searchInput.value.trim() });
            }, 300);
        });
    }

    if (classSelect) {
        attachClassSelectListener(classSelect);
    }

    window.addEventListener('popstate', function() {
        const params = new URLSearchParams(window.location.search);
        const classId = params.get('class_id') || '';
        const searchQuery = params.get('search') || '';
        if (searchInput) searchInput.value = searchQuery;
        loadDashboardContent({ classId, searchQuery });
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
        if (classSelect && classSelect.value !== urlClassId) {
            classSelect.value = urlClassId;
        }
    }
})();

// ========== HIGHLIGHT ROTATION ==========
const highlightSpan = document.getElementById('highlightText');
if (highlightSpan && typeof highlights !== 'undefined' && highlights.length > 0) {
    let currentIndex = 0;
    highlightSpan.textContent = highlights[0];
    setInterval(() => {
        highlightSpan.style.opacity = '0';
        setTimeout(() => {
            currentIndex = (currentIndex + 1) % highlights.length;
            highlightSpan.textContent = highlights[currentIndex];
            highlightSpan.style.opacity = '1';
        }, 300);
    }, 4000);
}

// ========== MODAL RESET CLASS ==========
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

// ========== ADD CLASS VIA AJAX ==========
document.getElementById('addClassForm')?.addEventListener('submit', function(e) {
    e.preventDefault();
    const form = this; const submitBtn = form.querySelector('button[type="submit"]'); const originalText = submitBtn.innerHTML;
    submitBtn.disabled = true; submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Creating...';
    const formData = new FormData(form); formData.append('is_ajax', 'true');
    fetch(DASHBOARD_URL.replace('/dashboard', '/add-class/'), { method: 'POST', headers: { 'X-CSRFToken': CSRF_TOKEN, 'X-Requested-With': 'XMLHttpRequest' }, body: formData })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'ok') {
            showNotification(data.message, 'success'); const className = document.getElementById('className').value; if (typeof addActivityLog === 'function') addActivityLog(`Class created: ${className}`);
            bootstrap.Modal.getInstance(document.getElementById('addClassModal')).hide();
            form.reset(); setTimeout(() => window.location.reload(), 1000);
        } else { showNotification(data.message || 'Failed', 'danger'); }
    })
    .catch(err => { console.error(err); showNotification('Network error', 'danger'); })
    .finally(() => { submitBtn.disabled = false; submitBtn.innerHTML = originalText; });
});