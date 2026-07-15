/**
 * UniForms – records list page (records.html)
 *
 * Loads records of one collection via REST API, renders the DataTables
 * table, workflow status filter bar, and admin actions (unlock, delete).
 *
 * Expects page-level constants defined inline by the template BEFORE
 * this script is loaded:
 *   COLLECTION_ID – current collection slug
 *   IS_ADMIN      – bool, current user is system_admin
 *   LIST_COLUMNS  – [{key, label}] extra columns from collection YAML
 *   TERM          – terminology strings (defined in base.html)
 *
 * All record-sourced values are escaped with escapeHtml() before being
 * interpolated into innerHTML (XSS protection – field values are user input).
 */

// DataTables column indices depend on LIST_COLUMNS.length
// 0: record_id, 1: status, 2: template, 3..(3+N-1): dynamic, 3+N: lock, 3+N+1: sort(hidden), 3+N+2: actions
const N = LIST_COLUMNS.length;
const SORT_COL_IDX    = 3 + N + 1;
const ACTIONS_COL_IDX = 3 + N + 2;

// Built from the first record loaded (all records in a deployment share the same workflow)
let statusConfig = {};  // id → {label, cls, style, priority}
let allRecords = [];
let activeFilter = new URLSearchParams(location.search).get('filter') || 'all';
let dt = null;
let pendingDeleteId = null;

function buildStatusConfig(workflowStates) {
    statusConfig = {};
    workflowStates.forEach((state, idx) => {
        const ba = badgeAttrs(state.color);
        statusConfig[state.id] = {
            label: state.label,
            cls: ba.cls,
            style: ba.style,
            priority: idx,
        };
    });
}

function buildFilterBar(workflowStates) {
    const bar = document.getElementById('filter-bar');
    workflowStates.forEach(state => {
        if (bar.querySelector(`[data-filter="${CSS.escape(state.id)}"]`)) return;
        const btn = document.createElement('button');
        btn.className = 'btn btn-sm filter-btn';
        btn.dataset.filter = state.id;
        btn.textContent = state.label;
        btn.addEventListener('click', () => setFilter(state.id));
        bar.appendChild(btn);
    });
}

// Generic field value extractor – searches all sections for a field with matching key
function getFieldValue(r, key) {
    for (const section of (r.data?.sections || [])) {
        const f = (section.fields || []).find(f => f.key === key);
        if (f != null && f.value != null && f.value !== '') return String(f.value);
    }
    return null;
}

function buildTableRows(records) {
    const tbody = document.getElementById('records-tbody');
    tbody.innerHTML = '';

    records.forEach(r => {
        const st = statusConfig[r.status] || {label: r.status, cls: 'bg-secondary-subtle text-secondary', style: '', priority: 99};
        const tr = document.createElement('tr');
        const recordId = escapeHtml(r.record_id);
        const lockBadge = r.locked_by
            ? `<span class="badge bg-warning-subtle text-warning border border-warning-subtle"><i class="bi bi-lock-fill me-1"></i>${escapeHtml(r.locked_by)}</span>`
            : '<span class="text-muted small">–</span>';

        const adminActions = IS_ADMIN ? `
            ${r.locked_by ? `<button class="btn btn-warning btn-sm" data-action="unlock" title="Unlock"><i class="bi bi-unlock"></i></button>` : ''}
            <button class="btn btn-danger btn-sm" data-action="delete" title="Delete"><i class="bi bi-trash"></i></button>
        ` : '';

        // Fixed columns
        let html = `
            <td class="ps-3 align-middle">
                <span class="badge bg-primary-subtle text-primary border border-primary-subtle fw-semibold">${recordId}</span>
            </td>
            <td class="align-middle"><span class="badge ${st.cls}" style="${st.style || ''}">${escapeHtml(st.label)}</span></td>
            <td class="align-middle small text-muted">${escapeHtml(r.data?.template_name || r.template_id)}</td>`;

        // Dynamic columns from collection list_columns
        LIST_COLUMNS.forEach(col => {
            const val = getFieldValue(r, col.key);
            html += `<td class="align-middle small">${val ? `<span>${escapeHtml(val)}</span>` : '<span class="text-muted fst-italic">–</span>'}</td>`;
        });

        // Lock + sort + actions
        html += `
            <td class="align-middle">${lockBadge}</td>
            <td class="d-none">${st.priority ?? 99}</td>
            <td class="align-middle text-end pe-3">
                <div class="d-flex gap-1 justify-content-end">
                    ${adminActions}
                    <a href="/records/${encodeURIComponent(COLLECTION_ID)}/${encodeURIComponent(r.record_id)}/print" target="_blank" class="btn btn-secondary btn-sm" title="${escapeHtml(TERM.btn_print)}">
                        <i class="bi bi-printer me-1"></i>${escapeHtml(TERM.btn_print)}
                    </a>
                    <a href="/records/${encodeURIComponent(COLLECTION_ID)}/${encodeURIComponent(r.record_id)}" class="btn btn-primary btn-sm">
                        <i class="bi bi-arrow-right me-1"></i>${escapeHtml(TERM.btn_open)}
                    </a>
                </div>
            </td>`;

        tr.innerHTML = html;
        // Action handlers are attached as listeners (record_id never lands in an inline onclick)
        tr.querySelector('[data-action="unlock"]')?.addEventListener('click', () => unlockRecord(r.record_id));
        tr.querySelector('[data-action="delete"]')?.addEventListener('click', () => confirmDelete(r.record_id));
        tbody.appendChild(tr);
    });
}

function applyFilter() {
    if (!dt) return;
    if (activeFilter === 'all') {
        dt.column(1).search('').draw();
    } else {
        const label = statusConfig[activeFilter]?.label || activeFilter;
        dt.column(1).search('^' + label + '$', true, false).draw();
    }
}

function setFilter(filter) {
    activeFilter = filter;
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.filter === filter);
    });
    applyFilter();
}

function confirmDelete(recordId) {
    pendingDeleteId = recordId;
    document.getElementById('deleteModalBody').textContent =
        `Delete ${recordId}? This action cannot be undone.`;
    new bootstrap.Modal(document.getElementById('deleteModal')).show();
}

function rebuildTable() {
    if (dt) { dt.destroy(); dt = null; }
    buildTableRows(allRecords);
    initDataTable();
    applyFilter();
}

document.getElementById('confirmDeleteBtn').addEventListener('click', async () => {
    if (!pendingDeleteId) return;
    bootstrap.Modal.getInstance(document.getElementById('deleteModal')).hide();
    const resp = await apiFetch(`/api/v1/records/${COLLECTION_ID}/${encodeURIComponent(pendingDeleteId)}`, {method: 'DELETE'});
    if (resp.ok || resp.status === 204) {
        allRecords = allRecords.filter(r => r.record_id !== pendingDeleteId);
        pendingDeleteId = null;
        rebuildTable();
    }
});

async function unlockRecord(recordId) {
    const resp = await apiFetch(`/api/v1/records/${COLLECTION_ID}/${encodeURIComponent(recordId)}/lock`, {method: 'DELETE'});
    if (resp.ok || resp.status === 204) {
        const r = allRecords.find(x => x.record_id === recordId);
        if (r) r.locked_by = null;
        rebuildTable();
    }
}

function initDataTable() {
    dt = $('#records-table').DataTable({
        order: [[SORT_COL_IDX, 'asc'], [0, 'desc']],
        columnDefs: [
            {orderable: false, targets: [ACTIONS_COL_IDX]},
            {visible: false, targets: [SORT_COL_IDX]},
        ],
        pageLength: 25,
    });
}

async function loadRecords() {
    try {
        const resp = await apiFetch(`/api/v1/records/${COLLECTION_ID}/`);
        if (!resp.ok) return;
        allRecords = await resp.json();
        document.getElementById('records-loading').classList.add('d-none');

        if (allRecords.length === 0) {
            document.getElementById('records-empty').classList.remove('d-none');
            return;
        }

        // Build status config + filter bar from the first record's workflow_states
        const firstWorkflow = allRecords[0]?.data?.workflow_states || [];
        if (firstWorkflow.length > 0) {
            buildStatusConfig(firstWorkflow);
            buildFilterBar(firstWorkflow);
        }

        buildTableRows(allRecords);
        document.getElementById('records-table-wrap').classList.remove('d-none');
        initDataTable();

        if (activeFilter !== 'all') setFilter(activeFilter);
    } catch (e) {
        document.getElementById('records-loading').innerHTML =
            `<div class="text-danger py-4">Error loading records: ${escapeHtml(e.message)}</div>`;
    }
}

document.querySelector('[data-filter="all"]').addEventListener('click', () => setFilter('all'));

if (activeFilter !== 'all') {
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.filter === activeFilter);
    });
}

loadRecords();
