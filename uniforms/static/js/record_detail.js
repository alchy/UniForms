/**
 * UniForms – record detail page (record_detail.html)
 *
 * Loads a record via REST API, renders the form through UniForms.render(),
 * and handles locking, saving, workflow status changes, Take Over and
 * print mode.
 *
 * Expects page-level constants defined inline by the template BEFORE
 * this script is loaded:
 *   COLLECTION_ID, RECORD_ID, CURRENT_USER – strings
 *   IS_ADMIN, PRINT_MODE                   – bools
 *
 * Values sourced from the record are escaped with escapeHtml() before
 * being interpolated into innerHTML.
 */

const RECORD_URL = `/api/v1/records/${encodeURIComponent(COLLECTION_ID)}/${encodeURIComponent(RECORD_ID)}`;

if (PRINT_MODE) document.body.classList.add('print-mode');

let recordDocument = null;
let collectionConfig = null;
let lockAcquired = false;
let statusConfig = {};   // built dynamically from record's workflow_states

// ---------------------------------------------------------------------------
// Workflow state UI – built from record.data.workflow_states after load
// ---------------------------------------------------------------------------

function buildWorkflowUI(workflowStates) {
    // Build statusConfig for badge rendering
    workflowStates.forEach(state => {
        const ba = badgeAttrs(state.color);
        statusConfig[state.id] = {
            label: state.label,
            cls: ba.cls,
            style: ba.style,
        };
    });

    // Build status dropdown
    const menu = document.getElementById('status-dropdown-menu');
    menu.innerHTML = '';
    workflowStates.forEach(state => {
        const li = document.createElement('li');
        const ba = badgeAttrs(state.color);
        const a = document.createElement('a');
        a.className = 'dropdown-item';
        a.href = '#';
        a.innerHTML = `<i class="bi bi-circle me-2 ${ba.iconCls}" style="${ba.iconStyle}"></i>${escapeHtml(state.label)}`;
        a.addEventListener('click', (e) => { e.preventDefault(); changeStatus(state.id); });
        li.appendChild(a);
        menu.appendChild(li);
    });
}

// ---------------------------------------------------------------------------
// Lock management
// ---------------------------------------------------------------------------

async function acquireLock() {
    try {
        const resp = await apiFetch(`${RECORD_URL}/lock`, {method: 'POST'});
        if (resp.ok) {
            lockAcquired = true;
            return true;
        } else if (resp.status === 423) {
            const err = await resp.json();
            const detail = err.detail || {};
            const lockedBy = detail.locked_by || '?';
            showLockBanner(`Being edited by <strong>${escapeHtml(lockedBy)}</strong>. Form is read-only.`);
            setReadOnly(true);
            return false;
        }
    } catch (e) {
        // Network error – allow editing without lock
    }
    return false;
}

async function releaseLock() {
    if (!lockAcquired) return;
    try {
        await fetch(`${RECORD_URL}/lock`, {
            method: 'DELETE',
            credentials: 'include',
            keepalive: true,
        });
    } catch (e) { /* ignore */ }
    lockAcquired = false;
}

async function forceUnlock() {
    await apiFetch(`${RECORD_URL}/lock`, {method: 'DELETE'});
    hideLockBanner();
    setReadOnly(false);
}

function showLockBanner(msg) {
    document.getElementById('lock-banner-msg').innerHTML = msg;
    document.getElementById('lock-banner').classList.remove('d-none');
}

function hideLockBanner() {
    document.getElementById('lock-banner').classList.add('d-none');
}

function setReadOnly(readonly) {
    document.getElementById('btn-save').disabled = readonly;
    document.getElementById('btn-save-leave').disabled = readonly;
    document.querySelectorAll('#sections-container input, #sections-container select, #sections-container textarea').forEach(el => {
        el.disabled = readonly;
    });
}

// ---------------------------------------------------------------------------
// Collection config – drives title_field and take_over behaviour
// ---------------------------------------------------------------------------

async function loadCollectionConfig() {
    try {
        const resp = await apiFetch(`/api/v1/collections/${encodeURIComponent(COLLECTION_ID)}`);
        if (resp.ok) collectionConfig = await resp.json();
    } catch (e) { /* non-fatal – falls back to defaults */ }
}

// Search for a field by key across all sections (including section_group children).
function findFieldInRecord(r, key) {
    for (const sec of (r.data?.sections || [])) {
        const f = (sec.fields || []).find(f => f.key === key);
        if (f) return f;
        for (const sub of (sec.sections || [])) {
            const sf = (sub.fields || []).find(f => f.key === key);
            if (sf) return sf;
        }
    }
    return null;
}

// Show Take Over button only when collection config declares take_over AND
// the target field actually exists in the loaded record.
function updateTakeOverButton(r) {
    const btn = document.getElementById('btn-takeover');
    if (collectionConfig?.take_over) {
        const field = findFieldInRecord(r, collectionConfig.take_over.field);
        if (field) {
            btn.classList.remove('d-none');
            return;
        }
    }
    btn.classList.add('d-none');
}

function getRecordTitle(r) {
    const key = collectionConfig?.title_field;
    if (key) {
        const f = findFieldInRecord(r, key);
        if (f?.value) return f.value;
    }
    return null;
}

function renderRecordHeader(r) {
    const st = statusConfig[r.status] || {label: r.status, cls: 'bg-secondary-subtle text-secondary', style: ''};
    const badge = document.getElementById('status-badge');
    badge.textContent = st.label;
    badge.className = `badge ${st.cls}`;
    badge.style.cssText = st.style || '';
    const title = getRecordTitle(r);
    document.getElementById('record-title').textContent = title || r.data.template_name || r.template_id;
    document.getElementById('record-meta').innerHTML =
        `<i class="bi bi-file-earmark-text me-1"></i>${escapeHtml(r.data.template_name || r.template_id)} &nbsp;·&nbsp; ` +
        `<i class="bi bi-person me-1"></i>${escapeHtml(r.created_by)} &nbsp;·&nbsp; ` +
        `<i class="bi bi-calendar me-1"></i>${new Date(r.created_at).toLocaleString()}`;
    updateTakeOverButton(r);
}

function buildSectionNav(sections) {
    const list = document.getElementById('section-nav-list');
    list.innerHTML = '';
    sections.forEach(s => {
        const li = document.createElement('li');
        li.className = 'nav-item';
        const a = document.createElement('a');
        a.href = `#sec-${s.id}`;
        a.className = 'nav-link py-1 small';
        a.textContent = s.title;
        li.appendChild(a);
        list.appendChild(li);
    });
}

// ---------------------------------------------------------------------------
// Record loading and rendering
// ---------------------------------------------------------------------------

async function loadRecord() {
    try {
        const resp = await apiFetch(RECORD_URL);
        if (!resp.ok) {
            showPageAlert('Record not found or access denied.');
            return;
        }
        const r = await resp.json();
        recordDocument = r;

        // Build workflow UI from the record's embedded workflow states
        const workflowStates = r.data?.workflow_states || [];
        buildWorkflowUI(workflowStates);

        renderRecordHeader(r);
        UniForms.render(r.data.sections || [], document.getElementById('sections-container'));
        buildSectionNav(r.data.sections || []);

        if (PRINT_MODE) {
            const title = getRecordTitle(r);
            const tbTitle = document.getElementById('print-tb-title');
            if (tbTitle) tbTitle.textContent = RECORD_ID + (title ? ' – ' + title : '');
            setTimeout(() => {
                document.querySelectorAll('.accordion-collapse:not(.show)').forEach(el => {
                    el.classList.add('show');
                });
                document.querySelectorAll(
                    '#sections-container .form-text, #sections-container .alert-info, ' +
                    '#sections-container .alert-warning, #sections-container .alert-secondary, ' +
                    '#sections-container .hint-classification'
                ).forEach(el => el.remove());
                document.querySelectorAll('#sections-container [placeholder]').forEach(el => el.removeAttribute('placeholder'));
            }, 150);
        } else {
            await acquireLock();
        }
    } catch (e) {
        showPageAlert('Error loading record: ' + e.message);
    }
}

// ---------------------------------------------------------------------------
// Save / status
// ---------------------------------------------------------------------------

function flashSaveIndicator() {
    const ind = document.getElementById('save-indicator');
    ind.classList.remove('d-none');
    setTimeout(() => ind.classList.add('d-none'), 3000);
}

async function saveRecord() {
    if (!recordDocument) return false;
    const btn = document.getElementById('btn-save');
    const spinner = document.getElementById('save-spinner');
    const icon = document.getElementById('save-icon');
    btn.disabled = true;
    spinner.classList.remove('d-none');
    icon.classList.add('d-none');

    try {
        const resp = await apiFetch(RECORD_URL, {
            method: 'PATCH',
            body: JSON.stringify({data: recordDocument.data}),
        });
        if (resp.ok) {
            const updated = await resp.json();
            recordDocument.updated_at = updated.updated_at;
            recordDocument.status = updated.status;
            renderRecordHeader(recordDocument);
            flashSaveIndicator();
            return true;
        } else if (resp.status === 423) {
            showPageAlert('Save failed – record is locked by another user.');
            return false;
        } else {
            showPageAlert('Save failed.');
            return false;
        }
    } finally {
        btn.disabled = false;
        spinner.classList.add('d-none');
        icon.classList.remove('d-none');
    }
}

async function saveAndLeave() {
    const btn = document.getElementById('btn-save-leave');
    const spinner = document.getElementById('save-leave-spinner');
    const icon = document.getElementById('save-leave-icon');
    btn.disabled = true;
    spinner.classList.remove('d-none');
    icon.classList.add('d-none');
    try {
        const ok = await saveRecord();
        if (ok) {
            await releaseLock();
            window.location.href = `/records/${encodeURIComponent(COLLECTION_ID)}`;
        }
    } finally {
        btn.disabled = false;
        spinner.classList.add('d-none');
        icon.classList.remove('d-none');
    }
}

async function changeStatus(newStatus) {
    if (!recordDocument) return;
    const resp = await apiFetch(RECORD_URL, {
        method: 'PATCH',
        body: JSON.stringify({status: newStatus, data: recordDocument.data}),
    });
    if (resp.ok) {
        const updated = await resp.json();
        recordDocument.status = updated.status;
        recordDocument.updated_at = updated.updated_at;
        renderRecordHeader(recordDocument);
        flashSaveIndicator();
    }
}

function showPageAlert(msg) {
    const el = document.getElementById('page-alert');
    el.textContent = msg;
    el.classList.remove('d-none');
}

async function loadFilePath() {
    try {
        const resp = await apiFetch('/api/v1/settings/');
        if (resp.ok) {
            const s = await resp.json();
            const dir = (s.records_dir || 'data/records').replace(/\\/g, '/');
            const path = dir + '/' + COLLECTION_ID + '/' + RECORD_ID + '.json';
            document.getElementById('record-filepath').textContent = path;
            document.getElementById('record-filepath-container').classList.remove('d-none');
            document.getElementById('record-filepath-container').classList.add('d-flex');
        }
    } catch (e) {}
}

function copyFilePath() {
    const path = document.getElementById('record-filepath').textContent;
    navigator.clipboard.writeText(path).then(() => {
        const btn = document.getElementById('copy-path-btn');
        btn.innerHTML = '<i class="bi bi-clipboard-check text-success" style="font-size:0.8rem;"></i>';
        setTimeout(() => { btn.innerHTML = '<i class="bi bi-clipboard" style="font-size:0.8rem;"></i>'; }, 2000);
    });
}

// Take Over – writes configured value into the take_over.field from collection config,
// saves the record, then reloads it so the rendered form reflects the new value.
// value_type "username" → current user; "timestamp" → current UTC ISO string.
async function takeover() {
    if (!recordDocument || !collectionConfig?.take_over) return;
    const { field: fieldKey, value_type } = collectionConfig.take_over;
    const value = (value_type === 'timestamp') ? new Date().toISOString() : CURRENT_USER;
    const field = findFieldInRecord(recordDocument, fieldKey);
    if (!field) return;
    field.value = value;
    const ok = await saveRecord();
    if (ok) await loadRecord();
}

async function init() {
    await loadCollectionConfig();
    await loadRecord();
    if (!PRINT_MODE) loadFilePath();
}
init();
