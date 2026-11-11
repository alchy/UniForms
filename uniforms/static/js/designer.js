/**
 * UniForms – Collection Designer (page logic)
 *
 * Drives /admin/designer/new and /admin/designer/{id}/edit:
 *
 *   collection wizard   Basics → Workflow → Records → Roles & terms → Templates → Review & save
 *   template designer   palette (drag or click) | canvas | attribute panel, live preview, YAML
 *
 * The page edits a *model* (the object a YAML file parses to) and sends it to
 * /api/v1/designer/*; the server converts it to YAML, validates and writes
 * it. All structural edits go through DesignerModel (designer_model.js).
 *
 * Security: every value is put into the DOM with textContent / properties via
 * h() – no user data is ever concatenated into HTML. The only renderer that
 * uses innerHTML is the shared UniForms.render() preview, which sanitizes.
 *
 * Everything lives inside this IIFE; the page adds no globals (main.js and
 * uniforms.js share the global scope with page scripts).
 */
(() => {
'use strict';

const M = window.DesignerModel;
const BOOT = window.DESIGNER_BOOT || {};
const API = '/api/v1/designer';
const $ = id => document.getElementById(id);

const STEPS = [
    {id: 'basics', label: 'Basics', icon: 'bi-info-circle'},
    {id: 'workflow', label: 'Workflow', icon: 'bi-diagram-3'},
    {id: 'records', label: 'Records', icon: 'bi-list-columns'},
    {id: 'roles', label: 'Roles & terms', icon: 'bi-people'},
    {id: 'templates', label: 'Templates', icon: 'bi-file-earmark-text'},
    {id: 'review', label: 'Review & save', icon: 'bi-check2-circle'},
];
const KIND_LABELS = {
    template: 'Template', section: 'Section', field: 'Field', column: 'Column',
    group: 'Step group', step: 'Step',
};
const SLUG_RE = /^[a-z0-9_-]+$/;

const S = {
    catalog: null,
    mode: BOOT.mode === 'edit' ? 'edit' : 'new',
    cid: BOOT.collectionId || null,
    model: null,        // collection model
    saved: null,        // JSON of the model as last loaded / saved
    source: null,       // {hash, comments, comments_lost, …} of the collection file
    templates: [],
    fieldKeys: [],
    step: 0,
    idTouched: false,
    tpl: null,          // open template: {isNew, templateId, filename, model, saved, source, …}
};

// ───────────────────────────────────────────────────────────────────────────
// DOM helpers
// ───────────────────────────────────────────────────────────────────────────

/** Create an element. Strings become text nodes – never HTML. */
function h(tag, attrs, ...children) {
    const el = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
        if (value === null || value === undefined || value === false) continue;
        if (key === 'class') el.className = value;
        else if (key === 'dataset') Object.assign(el.dataset, value);
        else if (key === 'style') el.style.cssText = value;
        else if (key.startsWith('on') && typeof value === 'function') el.addEventListener(key.slice(2), value);
        else if (key in el && key !== 'list') el[key] = value;
        else el.setAttribute(key, value === true ? '' : value);
    }
    const add = child => {
        if (child === null || child === undefined || child === false) return;
        if (Array.isArray(child)) child.forEach(add);
        else el.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
    };
    children.forEach(add);
    return el;
}

/** Append children to a parent, skipping null / false (Element.append would print "null"). */
function put(parent, ...children) {
    children.forEach(child => {
        if (child === null || child === undefined || child === false || child === '') return;
        if (Array.isArray(child)) put(parent, ...child);
        else parent.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
    });
    return parent;
}

const icon = (name, extra) => h('i', {class: `bi ${name}${extra ? ' ' + extra : ''}`});

function clear(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
    return el;
}

function badge(text, cls) {
    return h('span', {class: `badge ${cls || 'bg-light text-secondary border'}`}, text);
}

function iconButton(iconName, title, onClick, cls) {
    return h('button', {type: 'button', class: `btn btn-sm ${cls || 'btn-outline-secondary'}`, title,
                        'aria-label': title, onclick: onClick}, icon(iconName));
}

function formRow(label, control, help) {
    return h('div', {class: 'mb-3'},
        label ? h('label', {class: 'form-label small fw-semibold mb-1'}, label) : null,
        control,
        help ? h('div', {class: 'form-text'}, help) : null);
}

function showAlert(target, type, ...content) {
    const el = typeof target === 'string' ? $(target) : target;
    clear(el);
    if (!type) { el.classList.add('d-none'); return; }
    el.className = `alert alert-${type} py-2 small`;
    content.forEach(c => el.appendChild(c instanceof Node ? c : document.createTextNode(String(c))));
}

// ───────────────────────────────────────────────────────────────────────────
// API helpers
// ───────────────────────────────────────────────────────────────────────────

async function api(method, url, body) {
    const options = {method};
    if (body !== undefined) options.body = JSON.stringify(body);
    let res;
    try {
        res = await apiFetch(url, options);
    } catch (err) {
        return {ok: false, status: 0, data: {detail: 'Network error – the server cannot be reached'}};
    }
    let data = null;
    try { data = await res.json(); } catch (err) { data = null; }
    return {ok: res.ok, status: res.status, data};
}

/** Normalize an error response – `detail` may be a string, a {code, message} object or a list. */
function errInfo(r) {
    const d = r && r.data ? r.data.detail : null;
    if (typeof d === 'string') return {code: '', message: d, issues: []};
    if (Array.isArray(d)) {
        const message = d.map(x => (x && x.msg ? `${(x.loc || []).join('.')}: ${x.msg}` : String(x))).join('; ');
        return {code: '', message, issues: []};
    }
    if (d && typeof d === 'object') {
        return {code: d.code || '', message: d.message || JSON.stringify(d), issues: d.issues || []};
    }
    return {code: '', message: `Request failed (HTTP ${r ? r.status : '?'})`, issues: []};
}

const colUrl = () => `${API}/collections/${encodeURIComponent(S.cid)}`;

// ───────────────────────────────────────────────────────────────────────────
// Dialogs
// ───────────────────────────────────────────────────────────────────────────

/** Promise-based confirm dialog (Bootstrap modal #dz-confirm). */
function confirmDialog({title, message, detail, confirmLabel, danger}) {
    return new Promise(resolve => {
        const el = $('dz-confirm');
        $('dz-confirm-title').textContent = title;
        $('dz-confirm-message').textContent = message;
        $('dz-confirm-detail').textContent = detail || '';
        const ok = $('dz-confirm-ok');
        ok.textContent = confirmLabel || 'Confirm';
        ok.className = `btn btn-sm ${danger ? 'btn-danger' : 'btn-primary'}`;
        const modal = bootstrap.Modal.getOrCreateInstance(el);
        let answer = false;
        const onOk = () => { answer = true; modal.hide(); };
        const onHidden = () => {
            ok.removeEventListener('click', onOk);
            el.removeEventListener('hidden.bs.modal', onHidden);
            resolve(answer);
        };
        ok.addEventListener('click', onOk);
        el.addEventListener('hidden.bs.modal', onHidden);
        modal.show();
    });
}

/**
 * Run a save request; when the server answers that hand-written comments would
 * be lost, ask the user and repeat with confirm_rewrite.
 */
async function saveFlow(send) {
    let r = await send(false);
    if (!r.ok && errInfo(r).code === 'rewrite_not_confirmed') {
        const yes = await confirmDialog({
            title: 'Rewrite hand-written YAML?',
            message: errInfo(r).message,
            detail: 'The designer writes the file in its own canonical format. The leading comment block is kept, '
                + 'other comments are lost. The previous version is copied to the .designer_backup folder next to the file. '
                + 'To keep the comments, cancel and use the raw YAML editor instead.',
            confirmLabel: 'Rewrite file',
            danger: true,
        });
        if (!yes) return null;
        r = await send(true);
    }
    return r;
}

function issuesList(issues, emptyText) {
    if (!issues || !issues.length) {
        return emptyText ? h('div', {class: 'text-success small'}, icon('bi-check-circle', 'me-1'), emptyText) : null;
    }
    return h('ul', {class: 'list-unstyled small mb-0'}, issues.map(i => h('li', {class: 'mb-1'},
        icon(i.level === 'error' ? 'bi-x-circle-fill text-danger' : 'bi-exclamation-triangle-fill text-warning', 'me-1'),
        i.path ? h('code', {class: 'me-1'}, i.path) : null,
        i.message)));
}

// ───────────────────────────────────────────────────────────────────────────
// Generic bound controls
// ───────────────────────────────────────────────────────────────────────────

/**
 * Text input / textarea bound to obj[key]. `opts.owner()` may lazily create the
 * object on first edit (so merely viewing a step never changes the model).
 */
function boundText(getObj, key, opts) {
    const o = opts || {};
    const obj = getObj(false);
    const current = obj && obj[key] !== undefined && obj[key] !== null ? String(obj[key]) : '';
    const el = h(o.multiline ? 'textarea' : 'input', {
        class: `form-control form-control-sm${o.mono ? ' font-monospace' : ''}`,
        placeholder: o.placeholder || '',
        disabled: !!o.disabled,
        rows: o.multiline ? (o.rows || 3) : null,
        list: o.list || null,
        'aria-label': o.label || key,
    });
    if (!o.multiline) el.type = 'text';
    el.value = current;
    el.addEventListener('input', () => {
        const target = getObj(true);
        if (!target) return;
        if (o.before) o.before(el);
        if (o.write) o.write(target, el.value);
        else M.setProp(target, key, el.value, {keepNull: !!o.keepNull});
        if (o.after) o.after(el.value, el);
    });
    return el;
}

function boundCheck(label, checked, onChange, help) {
    const id = `dz-chk-${++boundCheck.seq}`;
    const input = h('input', {type: 'checkbox', class: 'form-check-input', id, checked: !!checked,
                              onchange: () => onChange(input.checked)});
    return h('div', {class: 'form-check mb-2'}, input,
        h('label', {class: 'form-check-label small', for: id}, label),
        help ? h('div', {class: 'form-text mt-0'}, help) : null);
}
boundCheck.seq = 0;

function selectBox(options, value, onChange, label) {
    const sel = h('select', {class: 'form-select form-select-sm', 'aria-label': label || 'Select',
                             onchange: () => onChange(sel.value)});
    let found = false;
    options.forEach(opt => {
        const o = h('option', {value: opt.value}, opt.label);
        if (String(opt.value) === String(value == null ? '' : value)) { o.selected = true; found = true; }
        sel.appendChild(o);
    });
    if (!found && value != null && value !== '') {
        const o = h('option', {value}, `${value} (custom)`);
        o.selected = true;
        sel.appendChild(o);
    }
    return sel;
}

/** Make the rows of a flat list reorderable by dragging their .dz-handle. */
function makeSortable(listEl, onMove) {
    let from = null;
    const rows = () => Array.from(listEl.children).filter(c => c.classList.contains('dz-sort-row'));
    rows().forEach((row, index) => {
        const handle = row.querySelector('.dz-handle');
        if (handle) {
            handle.addEventListener('mousedown', () => { row.draggable = true; });
            handle.addEventListener('mouseup', () => { row.draggable = false; });
        }
        row.addEventListener('dragstart', e => {
            from = index;
            row.classList.add('dz-dragging');
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', String(index));
        });
        row.addEventListener('dragend', () => { row.draggable = false; row.classList.remove('dz-dragging'); from = null; });
        row.addEventListener('dragover', e => { if (from !== null) { e.preventDefault(); row.classList.add('dz-drop-target'); } });
        row.addEventListener('dragleave', () => row.classList.remove('dz-drop-target'));
        row.addEventListener('drop', e => {
            e.preventDefault();
            row.classList.remove('dz-drop-target');
            if (from !== null && from !== index) onMove(from, index);
        });
    });
}

function moveInArray(list, from, to) {
    if (to < 0 || to >= list.length) return;
    list.splice(to, 0, list.splice(from, 1)[0]);
}

// ───────────────────────────────────────────────────────────────────────────
// Collection wizard
// ───────────────────────────────────────────────────────────────────────────

const colDirty = () => S.model !== null && JSON.stringify(S.model) !== S.saved;
const tplDirty = () => !!S.tpl && (S.tpl.isNew || JSON.stringify(S.tpl.model) !== S.tpl.saved);

function colChanged() {
    renderStepper();
    $('dz-title-name').textContent = S.model.name || (S.mode === 'new' ? 'New collection' : S.cid);
}

function ensureObj(parent, key) {
    if (!M.isObject(parent[key])) parent[key] = {};
    return parent[key];
}

function renderStepper() {
    const nav = clear($('dz-stepper'));
    STEPS.forEach((step, i) => {
        const locked = step.id === 'templates' && S.mode === 'new';
        const btn = h('button', {
            type: 'button',
            class: `nav-link d-flex align-items-center gap-2${i === S.step ? ' active' : ''}`,
            disabled: locked,
            title: locked ? 'Save the collection first – then add its templates' : '',
            onclick: () => goStep(i),
        }, h('span', {class: 'dz-step-no'}, String(i + 1)), step.label,
           step.id === 'review' && colDirty() ? h('span', {class: 'dz-dot', title: 'Unsaved changes'}) : null);
        nav.appendChild(h('li', {class: 'nav-item'}, btn));
    });
}

function goStep(i) {
    S.step = Math.max(0, Math.min(i, STEPS.length - 1));
    if (STEPS[S.step].id === 'templates' && S.mode === 'new') S.step += 1;
    renderStepper();
    renderStep();
    try { history.replaceState(null, '', `#${STEPS[S.step].id}`); } catch (err) { /* ignore */ }
}

function renderStep() {
    const pane = clear($('dz-step-pane'));
    const step = STEPS[S.step];
    ({basics: stepBasics, workflow: stepWorkflow, records: stepRecords, roles: stepRoles,
      templates: stepTemplates, review: stepReview})[step.id](pane);
    $('dz-prev').disabled = S.step === 0;
    $('dz-next').classList.toggle('d-none', S.step === STEPS.length - 1);
}

function stepHeader(title, text) {
    return h('div', {class: 'mb-3'}, h('h6', {class: 'fw-bold mb-1'}, title),
             h('div', {class: 'text-muted small'}, text));
}

// ── Step 1: basics ─────────────────────────────────────────────────────────

function stepBasics(pane) {
    const model = S.model;
    const idInput = boundText(() => model, 'id', {
        mono: true, disabled: S.mode === 'edit', placeholder: 'e.g. helpdesk', label: 'Collection id',
        write: (obj, v) => { obj.id = v.trim(); S.idTouched = true; },
        after: (v, el) => { el.classList.toggle('is-invalid', !!v && !SLUG_RE.test(v.trim())); colChanged(); },
    });
    const nameInput = boundText(() => model, 'name', {
        placeholder: 'e.g. IT Helpdesk', label: 'Name',
        write: (obj, v) => { obj.name = v; },
        after: v => {
            if (S.mode === 'new' && !S.idTouched) {
                model.id = M.slugify(v).replace(/_/g, '-').replace(/^item$/, '');
                idInput.value = model.id;
            }
            colChanged();
        },
    });
    put(pane,
        stepHeader('Collection basics', 'A collection groups records of one kind and gives them a workflow, an ID format and templates.'),
        h('div', {class: 'row'},
            h('div', {class: 'col-md-6'}, formRow('Name', nameInput, 'Shown in the sidebar and page titles.')),
            h('div', {class: 'col-md-6'}, formRow('Collection id', idInput,
                S.mode === 'edit'
                    ? 'The id is the file name and the key of user roles – it cannot be changed.'
                    : 'Lowercase letters, digits, "-" and "_". Becomes the file name data/collections/<id>.yaml.'))),
        formRow('Description', boundText(() => model, 'description', {multiline: true, rows: 3, after: colChanged,
            label: 'Description'}), 'Optional – shown on the collection page.'));
}

// ── Step 2: workflow ───────────────────────────────────────────────────────

function stepWorkflow(pane) {
    const model = S.model;
    put(pane, stepHeader('Workflow states', 'States a record moves through. New records start in the initial state. '
        + 'Existing records keep a copy of the states they were created with.'));
    const wf = M.isObject(model.workflow) ? model.workflow : null;
    const states = wf && Array.isArray(wf.states) ? wf.states : null;
    if (!states) {
        put(pane, h('div', {class: 'alert alert-info small py-2'},
            'This collection does not define its own states – the built-in defaults (New, Open, In Progress, On Hold, Closed) apply.'),
            h('button', {type: 'button', class: 'btn btn-primary btn-sm', onclick: () => {
                model.workflow = M.clone(S.catalog.defaults.collection.workflow);
                colChanged(); renderStep();
            }}, icon('bi-plus-circle', 'me-1'), 'Define states'));
        return;
    }
    const initial = wf.initial_state !== undefined ? wf.initial_state : 'new';
    const list = h('div', {class: 'dz-sort-list'});
    states.forEach((st, i) => {
        if (!M.isObject(st)) return;
        const preview = h('span', {class: 'badge'});
        const paint = () => {
            const ba = badgeAttrs(st.color);
            preview.className = `badge ${ba.cls}`;
            preview.style.cssText = ba.style;
            preview.textContent = st.label || st.id || 'state';
        };
        const isCustom = st.color && !S.catalog.state_colors.includes(st.color);
        const customInput = boundText(() => st, 'color', {placeholder: '#e74c3c or CSS color', label: 'Custom color',
            after: () => { paint(); colChanged(); }});
        customInput.classList.toggle('d-none', !isCustom);
        const colorSel = selectBox(
            S.catalog.state_colors.map(c => ({value: c, label: c})).concat([{value: '__custom', label: 'custom color…'}]),
            isCustom ? '__custom' : (st.color || 'secondary'),
            v => {
                if (v === '__custom') { customInput.classList.remove('d-none'); customInput.focus(); return; }
                customInput.classList.add('d-none');
                st.color = v; paint(); colChanged();
            }, 'Color');
        const radio = h('input', {type: 'radio', class: 'form-check-input', name: 'dz-initial', title: 'Initial state',
            'aria-label': 'Initial state', checked: st.id === initial,
            onchange: () => { wf.initial_state = st.id; colChanged(); }});
        const idInput = boundText(() => st, 'id', {mono: true, placeholder: 'id', label: 'State id',
            write: (obj, v) => {
                const wasInitial = (wf.initial_state !== undefined ? wf.initial_state : 'new') === obj.id;
                obj.id = v.trim();
                if (wasInitial) wf.initial_state = obj.id;
            },
            after: () => { paint(); colChanged(); }});
        list.appendChild(h('div', {class: 'dz-sort-row row g-2 align-items-center mb-2'},
            h('div', {class: 'col-auto'}, h('span', {class: 'dz-handle', title: 'Drag to reorder'}, icon('bi-grip-vertical'))),
            h('div', {class: 'col-auto'}, radio),
            h('div', {class: 'col-2'}, idInput),
            h('div', {class: 'col'}, boundText(() => st, 'label', {placeholder: 'Label', label: 'State label',
                after: () => { paint(); colChanged(); }})),
            h('div', {class: 'col-2'}, colorSel),
            h('div', {class: 'col-2'}, customInput),
            h('div', {class: 'col-2 text-center'}, preview),
            h('div', {class: 'col-auto btn-group'},
                iconButton('bi-arrow-up', 'Move up', () => { moveInArray(states, i, i - 1); colChanged(); renderStep(); }),
                iconButton('bi-arrow-down', 'Move down', () => { moveInArray(states, i, i + 1); colChanged(); renderStep(); }),
                iconButton('bi-trash', 'Remove state', () => {
                    states.splice(i, 1);
                    if (wf.initial_state === st.id && states.length) wf.initial_state = states[0].id;
                    colChanged(); renderStep();
                }, 'btn-outline-danger'))));
        paint();
    });
    makeSortable(list, (from, to) => { moveInArray(states, from, to); colChanged(); renderStep(); });
    put(pane,
        h('div', {class: 'row g-2 small text-muted mb-1'},
            h('div', {class: 'col-auto', style: 'width:2.2rem'}), h('div', {class: 'col-auto'}, 'Initial'),
            h('div', {class: 'col-2'}, 'Id'), h('div', {class: 'col'}, 'Label'), h('div', {class: 'col-2'}, 'Color'),
            h('div', {class: 'col-2'}), h('div', {class: 'col-2 text-center'}, 'Preview'), h('div', {class: 'col-auto', style: 'width:7rem'})),
        list,
        h('button', {type: 'button', class: 'btn btn-outline-primary btn-sm', onclick: () => {
            const id = M.uniqueName(states.filter(M.isObject).map(s => s.id), 'state_1');
            states.push({id, label: 'New state', color: 'secondary'});
            if (states.length === 1) wf.initial_state = id;
            colChanged(); renderStep();
        }}, icon('bi-plus-circle', 'me-1'), 'Add state'));
}

// ── Step 3: records (ID format, list columns, title, take over) ────────────

function fieldKeyDatalist() {
    return h('datalist', {id: 'dz-field-keys'},
        S.fieldKeys.map(f => h('option', {value: f.key}, f.label || f.key)));
}

function stepRecords(pane) {
    const model = S.model;
    const sample = h('code', {});
    const paintSample = () => { sample.textContent = M.sampleRecordId(M.isObject(model.id_format) ? model.id_format : {}); };
    const idf = () => (M.isObject(model.id_format) ? model.id_format : null);
    const formatInput = boundText(create => (create ? ensureObj(model, 'id_format') : idf()), 'format', {
        mono: true, placeholder: '{prefix}-{YYYYMM}-{rand:04d}', label: 'ID format',
        after: () => { paintSample(); colChanged(); }});
    const tokens = h('div', {class: 'd-flex flex-wrap gap-1 mt-1'}, S.catalog.id_tokens.map(t =>
        h('button', {type: 'button', class: 'btn btn-outline-secondary btn-sm py-0 font-monospace', title: 'Append token',
            onclick: () => {
                const target = ensureObj(model, 'id_format');
                target.format = (target.format || '') + t;
                formatInput.value = target.format; paintSample(); colChanged();
            }}, t)));
    paintSample();

    put(pane,
        stepHeader('Records', 'How record IDs look, which columns the record list shows and which field is the record title.'),
        fieldKeyDatalist(),
        h('h6', {class: 'small fw-bold text-uppercase text-muted'}, 'Record ID'),
        h('div', {class: 'row'},
            h('div', {class: 'col-md-3'}, formRow('Prefix', boundText(create => (create ? ensureObj(model, 'id_format') : idf()), 'prefix',
                {mono: true, placeholder: 'REC', label: 'ID prefix', after: () => { paintSample(); colChanged(); }}))),
            h('div', {class: 'col-md-6'}, formRow('Format', h('div', {}, formatInput, tokens))),
            h('div', {class: 'col-md-3'}, formRow('Example', h('div', {class: 'pt-1'}, sample)))));

    // List columns
    put(pane, h('h6', {class: 'small fw-bold text-uppercase text-muted mt-3'}, 'List columns'),
        h('div', {class: 'text-muted small mb-2'}, 'Extra columns of the record list. The key is a field key from the templates'
            + (S.fieldKeys.length ? ' – start typing to pick one.' : '.')));
    const cols = Array.isArray(model.list_columns) ? model.list_columns : null;
    const list = h('div', {class: 'dz-sort-list'});
    (cols || []).forEach((col, i) => {
        if (!M.isObject(col)) return;
        const labelInput = boundText(() => col, 'label', {placeholder: 'Column heading', label: 'Column label',
            write: (o, v) => { o.label = v; }, after: colChanged});
        list.appendChild(h('div', {class: 'dz-sort-row row g-2 align-items-center mb-2'},
            h('div', {class: 'col-auto'}, h('span', {class: 'dz-handle', title: 'Drag to reorder'}, icon('bi-grip-vertical'))),
            h('div', {class: 'col-4'}, boundText(() => col, 'key', {mono: true, placeholder: 'field key', list: 'dz-field-keys',
                label: 'Column field key',
                write: (o, v) => { o.key = v.trim(); },
                after: v => {
                    const known = S.fieldKeys.find(f => f.key === v.trim());
                    if (known && known.label && !col.label) { col.label = known.label; labelInput.value = known.label; }
                    colChanged();
                }})),
            h('div', {class: 'col'}, labelInput),
            h('div', {class: 'col-auto btn-group'},
                iconButton('bi-arrow-up', 'Move up', () => { moveInArray(cols, i, i - 1); colChanged(); renderStep(); }),
                iconButton('bi-arrow-down', 'Move down', () => { moveInArray(cols, i, i + 1); colChanged(); renderStep(); }),
                iconButton('bi-trash', 'Remove column', () => { cols.splice(i, 1); colChanged(); renderStep(); }, 'btn-outline-danger'))));
    });
    makeSortable(list, (from, to) => { moveInArray(cols, from, to); colChanged(); renderStep(); });
    if (!cols) list.appendChild(h('div', {class: 'text-muted small fst-italic mb-2'}, 'Not set – the default column (record_owner) is shown.'));
    put(pane, list, h('button', {type: 'button', class: 'btn btn-outline-primary btn-sm', onclick: () => {
        if (!Array.isArray(model.list_columns)) model.list_columns = [];
        model.list_columns.push({key: '', label: ''});
        colChanged(); renderStep();
    }}, icon('bi-plus-circle', 'me-1'), 'Add column'));

    // Title field + take over
    const to = M.isObject(model.take_over) ? model.take_over : null;
    const toBox = h('div', {class: 'row'});
    if (to) {
        put(toBox,
            h('div', {class: 'col-md-6'}, formRow('Target field', boundText(() => to, 'field', {mono: true, list: 'dz-field-keys',
                label: 'Take over field', write: (o, v) => { o.field = v.trim(); }, after: colChanged}),
                'Field that receives the value when the button is pressed.')),
            h('div', {class: 'col-md-6'}, formRow('Value written', selectBox(
                S.catalog.take_over_value_types.map(v => ({value: v, label: v === 'username' ? 'Current user name' : 'Current time (UTC)'})),
                to.value_type || 'username', v => { to.value_type = v; colChanged(); }, 'Take over value'))));
    }
    put(pane,
        h('h6', {class: 'small fw-bold text-uppercase text-muted mt-4'}, 'Record title'),
        h('div', {class: 'row'}, h('div', {class: 'col-md-6'}, formRow('Title field',
            boundText(() => model, 'title_field', {mono: true, list: 'dz-field-keys', keepNull: true, label: 'Title field', after: colChanged}),
            'Field shown as the heading of a record. Empty = the template name is used.'))),
        h('h6', {class: 'small fw-bold text-uppercase text-muted mt-3'}, '"Take over" button'),
        boundCheck('Show a Take over button on the record page', !!to, on => {
            if (on) model.take_over = {field: 'record_owner', value_type: 'username'};
            else delete model.take_over;
            colChanged(); renderStep();
        }),
        toBox);
}

// ── Step 4: roles & terminology ────────────────────────────────────────────

function stepRoles(pane) {
    const model = S.model;
    const ROLE_HELP = {
        collection_admin: 'Manages records and templates of the collection, assigns users, deletes records.',
        collection_user: 'Creates and edits records, reads templates.',
    };
    put(pane, stepHeader('Roles & terminology', 'Names of the two collection roles and the wording used in this collection. '
        + 'Users are assigned to roles in Admin → Users.'));
    const roleRow = id => {
        const find = () => (Array.isArray(model.roles) ? model.roles.find(r => M.isObject(r) && r.id === id) : null);
        return h('div', {class: 'col-md-6'}, formRow(id, boundText(create => {
            if (!create) return find();
            if (!Array.isArray(model.roles)) model.roles = S.catalog.role_ids.map(r => ({id: r, label: ''}));
            if (!find()) model.roles.push({id, label: ''});
            return find();
        }, 'label', {placeholder: 'Display name', label: `Label of ${id}`, write: (o, v) => { o.label = v; }, after: colChanged}),
        ROLE_HELP[id] || ''));
    };
    put(pane, h('h6', {class: 'small fw-bold text-uppercase text-muted'}, 'Roles'),
        h('div', {class: 'row'}, S.catalog.role_ids.map(roleRow)));

    put(pane, h('h6', {class: 'small fw-bold text-uppercase text-muted mt-3'}, 'Terminology'),
        h('div', {class: 'text-muted small mb-2'}, 'Leave a text empty to use the global wording (shown in grey).'));
    const term = () => (M.isObject(model.terminology) ? model.terminology : null);
    const known = S.catalog.terminology_keys.map(t => t.key);
    const extra = Object.keys(term() || {}).filter(k => !known.includes(k)).map(k => ({key: k, default: ''}));
    const grid = h('div', {class: 'row'});
    S.catalog.terminology_keys.concat(extra).forEach(t => {
        grid.appendChild(h('div', {class: 'col-md-6'}, formRow(null, h('div', {class: 'input-group input-group-sm'},
            h('span', {class: 'input-group-text font-monospace dz-term-key'}, t.key),
            boundText(create => (create ? ensureObj(model, 'terminology') : term()), t.key, {
                placeholder: t.default, label: `Terminology ${t.key}`,
                after: () => {
                    if (term() && !Object.keys(term()).length) delete model.terminology;
                    colChanged();
                }})))));
    });
    put(pane, grid);
}

// ── Step 5: templates ──────────────────────────────────────────────────────

async function refreshTemplates() {
    const r = await api('GET', colUrl());
    if (r.ok) {
        S.templates = r.data.templates || [];
        S.fieldKeys = r.data.field_keys || [];
    }
}

function stepTemplates(pane) {
    put(pane, h('div', {class: 'd-flex justify-content-between align-items-start'},
        stepHeader('Templates', 'Form templates of this collection. Each template is saved on its own – '
            + 'open one to design its sections and fields.'),
        h('button', {type: 'button', class: 'btn btn-success btn-sm', onclick: openNewTemplateDialog},
            icon('bi-plus-circle', 'me-1'), 'New template')));
    if (!S.templates.length) {
        put(pane, h('div', {class: 'dz-empty py-4'}, 'No templates yet – create the first one.'));
        return;
    }
    const tbody = h('tbody', {});
    S.templates.forEach(t => {
        const canDesign = t.loadable && t.template_id;
        const rawHref = t.template_id ? `/templates/${encodeURIComponent(S.cid)}/${encodeURIComponent(t.template_id)}/edit` : null;
        tbody.appendChild(h('tr', {},
            h('td', {class: 'ps-3 align-middle'}, h('div', {class: 'fw-semibold'}, t.name || '–'),
                h('code', {class: 'small'}, t.template_id || '(no template_id)')),
            h('td', {class: 'align-middle small text-muted'}, t.filename),
            h('td', {class: 'align-middle'},
                t.status ? badge(t.status, t.status === 'active' ? 'bg-success-subtle text-success border border-success-subtle' : null) : null, ' ',
                t.abstract ? badge('abstract') : null, ' ',
                t.extends ? badge(`extends ${t.extends}`) : null, ' ',
                !t.loadable ? badge('raw editor only', 'bg-warning-subtle text-warning-emphasis border border-warning-subtle') : null),
            h('td', {class: 'align-middle small text-muted'}, `${t.sections} section${t.sections === 1 ? '' : 's'}`),
            h('td', {class: 'align-middle text-end pe-3'}, h('div', {class: 'd-flex gap-1 justify-content-end'},
                canDesign ? h('button', {type: 'button', class: 'btn btn-primary btn-sm', onclick: () => openTemplate(t.template_id)},
                    icon('bi-bricks', 'me-1'), 'Design') : null,
                rawHref ? h('a', {class: 'btn btn-outline-secondary btn-sm', href: rawHref, title: 'Raw YAML editor'}, icon('bi-code-slash')) : null,
                t.template_id ? iconButton('bi-trash', 'Delete template', () => deleteTemplate(t), 'btn-outline-danger') : null))));
    });
    put(pane, h('div', {class: 'card border'}, h('div', {class: 'table-responsive'},
        h('table', {class: 'table table-hover mb-0'},
            h('thead', {class: 'table-light'}, h('tr', {},
                h('th', {class: 'ps-3'}, 'Template'), h('th', {}, 'File'), h('th', {}, 'Status'), h('th', {}, 'Content'), h('th', {}))),
            tbody))));
}

async function deleteTemplate(t) {
    const children = S.templates.filter(x => x.extends === t.template_id).map(x => x.template_id);
    const yes = await confirmDialog({
        title: 'Delete template',
        message: `Really delete template "${t.name || t.template_id}" (${t.filename})?`,
        detail: (children.length ? `Templates extending it will lose the inherited sections: ${children.join(', ')}. ` : '')
            + 'Existing records are not affected.',
        confirmLabel: 'Delete', danger: true,
    });
    if (!yes) return;
    const r = await api('DELETE', `/api/v1/templates/${encodeURIComponent(S.cid)}/${encodeURIComponent(t.template_id)}`);
    if (r.ok) showToast('Template deleted');
    else showToast(errInfo(r).message, 'danger');
    await refreshTemplates();
    renderStep();
}

function openNewTemplateDialog() {
    const nameEl = $('dz-nt-name'), idEl = $('dz-nt-id'), fileEl = $('dz-nt-file');
    const extEl = clear($('dz-nt-extends'));
    extEl.appendChild(h('option', {value: ''}, '– none –'));
    S.templates.filter(t => t.template_id && t.loadable).forEach(t =>
        extEl.appendChild(h('option', {value: t.template_id}, `${t.name || t.template_id}${t.abstract ? ' (abstract)' : ''}`)));
    nameEl.value = ''; idEl.value = ''; fileEl.value = '';
    $('dz-nt-abstract').checked = false;
    idEl.dataset.touched = ''; fileEl.dataset.touched = '';
    showAlert('dz-nt-alert', null);
    bootstrap.Modal.getOrCreateInstance($('dz-new-template')).show();
}

function wireNewTemplateDialog() {
    const nameEl = $('dz-nt-name'), idEl = $('dz-nt-id'), fileEl = $('dz-nt-file');
    const derive = () => {
        if (!idEl.dataset.touched) {
            const slug = M.slugify(nameEl.value).replace(/_/g, '-');
            idEl.value = nameEl.value.trim() ? `${slug}-v1` : '';
        }
        if (!fileEl.dataset.touched) fileEl.value = idEl.value.toLowerCase().replace(/[^a-z0-9_-]/g, '_').replace(/-/g, '_');
    };
    nameEl.addEventListener('input', derive);
    idEl.addEventListener('input', () => { idEl.dataset.touched = '1'; derive(); });
    fileEl.addEventListener('input', () => { fileEl.dataset.touched = '1'; });
    $('dz-nt-create').addEventListener('click', () => {
        const name = nameEl.value.trim(), id = idEl.value.trim(), file = fileEl.value.trim();
        const problem = !name ? 'Enter a template name.'
            : !/^[A-Za-z0-9_-]+$/.test(id) ? 'Template id may only contain letters, digits, "-" and "_".'
            : S.templates.some(t => t.template_id === id) ? `Template id "${id}" already exists.`
            : !SLUG_RE.test(file) ? 'File name may only contain lowercase letters, digits, "-" and "_".'
            : S.templates.some(t => t.filename === `${file}.yaml`) ? `File "${file}.yaml" already exists.` : null;
        if (problem) { showAlert('dz-nt-alert', 'danger', problem); return; }
        const model = M.clone(S.catalog.defaults.template);
        model.template_id = id;
        model.name = name;
        const parent = $('dz-nt-extends').value;
        if ($('dz-nt-abstract').checked) M.renameKey(model, 'description', 'abstract', true);
        else delete model.description;
        if (parent) { model.extends = parent; model.sections = []; }
        // keep `sections` as the last key (readable YAML)
        const sections = model.sections; delete model.sections; model.sections = sections;
        bootstrap.Modal.getOrCreateInstance($('dz-new-template')).hide();
        startTemplate({isNew: true, templateId: id, filename: file, model, source: null,
                       inherited: {chain: [], sections: [], error: null}});
    });
}

// ── Step 6: review & save ──────────────────────────────────────────────────

async function stepReview(pane) {
    const model = S.model;
    put(pane, stepHeader('Review & save', 'The collection settings are checked by the server and written to its YAML file. '
        + 'Templates are saved separately in the Templates step.'));
    const cid = S.mode === 'edit' ? S.cid : String(model.id || '').trim();
    if (!SLUG_RE.test(cid)) {
        put(pane, h('div', {class: 'alert alert-danger small py-2'}, 'Enter a valid collection id in the Basics step first.'));
        return;
    }
    const body = h('div', {}, h('div', {class: 'text-muted small'}, h('span', {class: 'spinner-border spinner-border-sm me-2'}), 'Checking…'));
    put(pane, body);
    const stepAtStart = S.step;
    const r = await api('POST', `${API}/collections/${encodeURIComponent(cid)}/check`, {model});
    if (S.step !== stepAtStart) return;
    clear(body);
    if (!r.ok) { put(body, h('div', {class: 'alert alert-danger small py-2'}, errInfo(r).message)); return; }
    const check = r.data;
    const dirty = colDirty();
    const status = S.mode === 'new' ? ['primary', 'New collection – not saved yet']
        : dirty ? ['warning', 'Unsaved changes'] : ['success', 'No changes – the file is up to date'];
    const saveBtn = h('button', {type: 'button', class: 'btn btn-success', disabled: !check.ok || (S.mode === 'edit' && !dirty),
        onclick: () => saveCollection(saveBtn)}, icon('bi-save', 'me-1'), S.mode === 'new' ? 'Create collection' : 'Save collection');
    const resultBox = h('div', {id: 'dz-save-result', class: 'd-none'});
    put(body,
        h('div', {class: 'd-flex align-items-center gap-3 mb-3 flex-wrap'},
            h('span', {class: `badge text-bg-${status[0]}`}, status[1]),
            h('span', {class: 'small text-muted'}, 'File: ', h('code', {}, `data/collections/${cid}.yaml`)),
            h('div', {class: 'ms-auto'}, saveBtn)),
        resultBox);
    if (S.source && S.source.rewrite_lossy && dirty) {
        put(body, h('div', {class: 'alert alert-warning small py-2'}, icon('bi-exclamation-triangle', 'me-1'),
            `This file was written by hand: ${S.source.comments_lost} comment line(s)`
            + (S.source.anchors ? ` and ${S.source.anchors} YAML anchor(s)` : '')
            + ' will be lost when the designer rewrites it (you will be asked to confirm; a backup is kept). ',
            h('a', {href: `/admin/collections/${encodeURIComponent(cid)}/edit`}, 'Open the raw YAML editor instead')));
    }
    put(body,
        h('div', {class: 'card border mb-3'}, h('div', {class: 'card-header small fw-semibold'}, 'Validation'),
            h('div', {class: 'card-body py-2'}, issuesList(check.issues, 'No problems found.'))),
        h('div', {class: 'card border'}, h('div', {class: 'card-header small fw-semibold'}, 'YAML that will be written'),
            h('pre', {class: 'dz-yaml mb-0'}, check.yaml || '')));
}

async function saveCollection(btn) {
    btn.disabled = true;
    const cid = S.mode === 'edit' ? S.cid : String(S.model.id || '').trim();
    const r = await saveFlow(confirm => (S.mode === 'new'
        ? api('POST', `${API}/collections`, {collection_id: cid, model: S.model})
        : api('PUT', colUrl(), {model: S.model, base_hash: S.source ? S.source.hash : null, confirm_rewrite: confirm})));
    btn.disabled = false;
    if (!r) return;
    const box = $('dz-save-result');
    if (!r.ok) {
        const e = errInfo(r);
        box.className = 'alert alert-danger small py-2';
        put(clear(box), h('div', {class: 'fw-semibold'}, e.message), issuesList(e.issues) || '');
        if (e.code === 'stale') {
            put(box, h('button', {type: 'button', class: 'btn btn-sm btn-outline-danger mt-2',
                onclick: () => window.location.reload()}, 'Reload from disk (discards your changes)'));
        }
        return;
    }
    S.saved = JSON.stringify(S.model);
    S.source = r.data.source;
    if (S.mode === 'new') {
        showToast('Collection created');
        window.location.href = `/admin/designer/${encodeURIComponent(cid)}/edit#templates`;
        return;
    }
    showToast(r.data.change === 'unchanged' ? 'Nothing to save – file unchanged' : 'Collection saved');
    renderStepper();
    renderStep();
}

// ───────────────────────────────────────────────────────────────────────────
// Template designer
// ───────────────────────────────────────────────────────────────────────────

let drag = null;          // {src: 'palette'|'canvas', kind, type?, path?}
let dropTarget = null;    // {listPath, index}
let checkTimer = null;
let checkSeq = 0;
let undoKey = null;

function paletteItems() {
    return [
        {title: 'Sections', items: S.catalog.section_types.map(t => ({kind: 'section', type: t.type, label: t.label, icon: t.icon, hint: t.description}))},
        {title: 'Fields', items: S.catalog.field_types.map(t => ({kind: 'field', type: t.type, label: t.label, icon: t.icon}))
            .concat([{kind: 'field', type: 'auto', label: 'Automatic value', icon: 'bi-magic', hint: 'Read-only field filled by the system (record ID, user, time…)'}])},
        {title: 'Table', items: [
            {kind: 'column', type: 'text', label: 'Text column', icon: 'bi-layout-three-columns'},
            {kind: 'column', type: 'select', label: 'Select column', icon: 'bi-menu-button-wide'}]},
        {title: 'Checklist', items: [
            {kind: 'group', type: null, label: 'Step group', icon: 'bi-collection'},
            {kind: 'step', type: null, label: 'Step', icon: 'bi-check2-square'}]},
    ];
}

function sectionMeta(type) {
    return S.catalog.section_types.find(t => t.type === type) || {label: type || 'custom', icon: 'bi-puzzle', children: null};
}

function fieldIcon(type) {
    const ft = S.catalog.field_types.find(t => t.type === (type || 'text'));
    return ft ? ft.icon : 'bi-question-square';
}

async function openTemplate(templateId) {
    const r = await api('GET', `${colUrl()}/templates/${encodeURIComponent(templateId)}`);
    if (!r.ok) { showToast(errInfo(r).message, 'danger'); return; }
    startTemplate({isNew: false, templateId, filename: r.data.filename, model: r.data.model,
                   source: r.data.source, inherited: r.data.inherited});
}

function startTemplate(t) {
    S.tpl = Object.assign({saved: t.isNew ? null : JSON.stringify(t.model), sel: [], undo: [], check: null,
                           view: 'design', live: false, fileTouched: false}, t);
    undoKey = null;
    $('dz-collection-view').classList.add('d-none');
    $('dz-template-view').classList.remove('d-none');
    renderPalette();
    renderTemplate();
    scheduleCheck(0);
    window.scrollTo(0, 0);
}

async function closeTemplate() {
    if (tplDirty()) {
        const yes = await confirmDialog({title: 'Discard changes?', message: 'This template has unsaved changes.',
            detail: 'They will be lost if you leave the template designer now.', confirmLabel: 'Discard changes', danger: true});
        if (!yes) return;
    }
    S.tpl = null;
    $('dz-template-view').classList.add('d-none');
    $('dz-collection-view').classList.remove('d-none');
    await refreshTemplates();
    goStep(STEPS.findIndex(s => s.id === 'templates'));
}

function pushUndo(key) {
    const t = S.tpl;
    if (key && key === undoKey) return;       // coalesce typing in one control
    undoKey = key || null;
    t.undo.push(JSON.stringify({model: t.model, sel: t.sel}));
    if (t.undo.length > 60) t.undo.shift();
}

function undo() {
    const t = S.tpl;
    if (!t.undo.length) return;
    const snap = JSON.parse(t.undo.pop());
    t.model = snap.model;
    t.sel = snap.sel && M.get(t.model, snap.sel) !== undefined ? snap.sel : [];
    undoKey = null;
    renderTemplate();
    scheduleCheck();
}

/** Structural change: remember undo state, run `fn`, redraw everything. */
function mutate(fn) {
    pushUndo(null);
    const result = fn();
    renderTemplate();
    scheduleCheck();
    return result;
}

/** Attribute edit from the panel: redraw the canvas only (the focused input must survive). */
function edited(el, rerenderProps) {
    renderCanvas();
    renderToolbar();
    if (rerenderProps) renderProps();
    scheduleCheck();
}

function select(path) {
    S.tpl.sel = path;
    undoKey = null;
    highlightSelection();
    renderProps();
}

function renderTemplate() {
    renderToolbar();
    renderCanvas();
    renderProps();
    applyView();
}

function renderToolbar() {
    const t = S.tpl;
    $('dz-tpl-name').textContent = t.model.name || t.templateId || 'New template';
    const meta = clear($('dz-tpl-meta'));
    put(meta, h('code', {class: 'me-2'}, t.model.template_id || ''), h('span', {class: 'text-muted me-2'}, `${t.filename}${/\.yaml$/.test(t.filename) ? '' : '.yaml'}`));
    if (t.isNew) put(meta, badge('new – not saved', 'text-bg-primary'), ' ');
    else if (tplDirty()) put(meta, badge('unsaved changes', 'text-bg-warning'), ' ');
    $('dz-tpl-undo').disabled = !t.undo.length;
    $('dz-tpl-save').disabled = !tplDirty();
    const raw = $('dz-tpl-raw');
    raw.classList.toggle('d-none', t.isNew);
    if (!t.isNew) raw.href = `/templates/${encodeURIComponent(S.cid)}/${encodeURIComponent(t.templateId)}/edit`;
    const warn = $('dz-tpl-source-warning');
    if (!t.isNew && t.source && t.source.rewrite_lossy) {
        showAlert(warn, 'warning', icon('bi-exclamation-triangle', 'me-1'),
            `This file was written by hand: ${t.source.comments_lost} comment line(s)`
            + (t.source.anchors ? ` and ${t.source.anchors} YAML anchor(s)` : '')
            + ' will be lost when the designer saves a change (you will be asked to confirm; a backup is kept).');
    } else {
        showAlert(warn, null);
    }
}

function applyView() {
    const t = S.tpl;
    document.querySelectorAll('#dz-tpl-tabs [data-view]').forEach(btn =>
        btn.classList.toggle('active', btn.dataset.view === t.view));
    $('dz-design-row').classList.toggle('d-none', t.view !== 'design');
    $('dz-preview-wrap').classList.toggle('d-none', !(t.view === 'preview' || (t.view === 'design' && t.live)));
    $('dz-yaml-wrap').classList.toggle('d-none', t.view !== 'yaml');
    $('dz-live-toggle').checked = t.live;
    renderCheckResult();
}

// ── Palette ────────────────────────────────────────────────────────────────

function renderPalette() {
    const box = clear($('dz-palette'));
    paletteItems().forEach(group => {
        box.appendChild(h('div', {class: 'dz-palette-title'}, group.title));
        group.items.forEach(item => {
            box.appendChild(h('div', {
                class: 'dz-palette-item', draggable: true, tabIndex: 0, role: 'button',
                title: `${item.hint ? item.hint + ' – ' : ''}drag onto the canvas or click to add`,
                ondragstart: e => {
                    drag = {src: 'palette', kind: item.kind, type: item.type};
                    e.dataTransfer.effectAllowed = 'copy';
                    e.dataTransfer.setData('text/plain', item.label);
                },
                ondragend: endDrag,
                onclick: () => addFromPalette(item.kind, item.type),
                onkeydown: e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); addFromPalette(item.kind, item.type); } },
            }, icon(item.icon, 'me-2'), item.label));
        });
    });
}

/** Where a click on a palette item puts the new node: near the selection, else the last fitting place. */
function targetListFor(kind, type) {
    const model = S.tpl.model;
    const sel = S.tpl.sel || [];
    const item = {type};
    const childKey = {field: 'fields', column: 'columns', group: 'step_groups', step: 'steps'}[kind];
    const after = listPath => (M.isPrefix(listPath, sel) && sel.length === listPath.length + 1 ? sel[sel.length - 1] + 1 : null);

    if (kind === 'section') {
        for (let n = sel.length; n >= 2; n--) {
            const node = M.get(model, sel.slice(0, n));
            if (M.isObject(node) && node.type === 'section_group' && M.kindOf(sel.slice(0, n)) === 'section') {
                const lp = sel.slice(0, n).concat('subsections');
                if (M.canDrop(model, 'section', lp, item)) return {listPath: lp, index: after(lp)};
            }
        }
        return {listPath: ['sections'], index: sel.length >= 2 ? sel[1] + 1 : null};
    }
    const tryOwner = ownerPath => {
        const owner = M.get(model, ownerPath);
        if (!M.isObject(owner)) return null;
        if (kind === 'step' && owner.type === 'checklist' && 'step_groups' in owner) {
            if (!Array.isArray(owner.step_groups) || !owner.step_groups.length) return null;
            const lp = ownerPath.concat('step_groups', owner.step_groups.length - 1, 'steps');
            return M.canDrop(model, kind, lp) ? {listPath: lp, index: null} : null;
        }
        const lp = ownerPath.concat(childKey);
        return M.canDrop(model, kind, lp) ? {listPath: lp, index: after(lp)} : null;
    };
    for (let n = sel.length; n >= 2; n -= 2) {
        const found = tryOwner(sel.slice(0, n));
        if (found) return found;
    }
    let fallback = null;
    M.walkSections(model, (sec, path) => { fallback = tryOwner(path) || fallback; });
    return fallback;
}

function addFromPalette(kind, type) {
    const target = targetListFor(kind, type);
    if (!target) {
        const need = {field: 'a header or form section', column: 'a table section', group: 'a checklist section',
                      step: 'a checklist section'}[kind] || 'a section';
        showToast(`Add or select ${need} first`, 'warning');
        return;
    }
    addItem(kind, type, target.listPath, target.index);
}

function addItem(kind, type, listPath, index) {
    const model = S.tpl.model;
    mutate(() => {
        const existed = Array.isArray(M.get(model, listPath));
        const item = M.newItem(kind, type, model, existed ? M.get(model, listPath) : []);
        S.tpl.sel = M.insert(model, listPath, existed ? index : null, item) || S.tpl.sel;
    });
}

// ── Canvas ─────────────────────────────────────────────────────────────────

const pathAttr = path => JSON.stringify(path);

function itemAttrs(path, extraClass) {
    return {class: `dz-item ${extraClass || ''}`, draggable: true, tabIndex: 0, dataset: {path: pathAttr(path)}};
}

function listEl(listPath, kind, emptyText, children) {
    const el = h('div', {class: 'dz-list', dataset: {list: pathAttr(listPath), kind}}, children);
    if (!children.length && emptyText) el.appendChild(h('div', {class: 'dz-empty'}, emptyText));
    return el;
}

function fieldRow(path, field, kind) {
    if (!M.isObject(field)) {
        return h('div', {class: 'dz-row dz-locked'}, icon('bi-lock', 'me-1'), `Unsupported ${kind} – edit in raw YAML`);
    }
    const auto = kind === 'field' ? M.getAuto(field) : '';
    return h('div', itemAttrs(path, 'dz-row'),
        icon('bi-grip-vertical', 'dz-handle'),
        icon(auto ? 'bi-magic' : fieldIcon(field.type), 'text-secondary'),
        h('span', {class: 'dz-row-label'}, field.label || h('em', {class: 'text-muted'}, '(no label)')),
        h('code', {class: 'dz-row-key'}, field.key || '?'),
        auto ? badge(`auto: ${auto}`) : null,
        (field.type === 'select' && Array.isArray(field.options)) ? badge(`${field.options.length} options`) : null,
        field.required ? badge('required', 'bg-danger-subtle text-danger border border-danger-subtle') : null,
        (field.visible_if || field.required_if) ? badge('conditional', 'bg-info-subtle text-info-emphasis border border-info-subtle') : null,
        (!auto && !M.isEditable(field, kind)) ? badge('read-only') : null);
}

function stepRow(path, step) {
    const obj = M.isObject(step);
    if (!obj && typeof step !== 'string') {
        return h('div', {class: 'dz-row dz-locked'}, icon('bi-lock', 'me-1'), 'Unsupported step – edit in raw YAML');
    }
    return h('div', itemAttrs(path, 'dz-row'),
        icon('bi-grip-vertical', 'dz-handle'), icon('bi-square', 'text-secondary'),
        h('span', {class: 'dz-row-label'}, M.stepAction(step) || h('em', {class: 'text-muted'}, '(no text)')),
        obj && step.hint ? badge('hint') : null,
        obj && step.example ? badge('example') : null);
}

function stepList(listPath, steps) {
    return listEl(listPath, 'step', 'Drop steps here', (Array.isArray(steps) ? steps : []).map((s, i) => stepRow(listPath.concat(i), s)));
}

function groupCard(path, group) {
    if (!M.isObject(group)) return h('div', {class: 'dz-row dz-locked'}, icon('bi-lock', 'me-1'), 'Unsupported group – edit in raw YAML');
    return h('div', itemAttrs(path, 'dz-group'),
        h('div', {class: 'dz-group-head'}, icon('bi-grip-vertical', 'dz-handle'), icon('bi-collection', 'text-secondary'),
            h('span', {class: 'fw-semibold'}, group.title || h('em', {class: 'text-muted fw-normal'}, '(untitled group)')),
            group.note ? h('small', {class: 'text-muted'}, `(${group.note})`) : null),
        h('div', {class: 'dz-group-body'}, stepList(path.concat('steps'), group.steps)));
}

function sectionBody(path, sec) {
    const type = sec.type;
    if (type === 'section_group') {
        const subs = Array.isArray(sec.subsections) ? sec.subsections : [];
        const out = [listEl(path.concat('subsections'), 'section', 'Drop form, table or checklist sections here',
            subs.map((s, i) => sectionCard(path.concat('subsections', i), s)))];
        if ('sections' in sec && !('subsections' in sec)) {
            out.unshift(h('div', {class: 'text-warning-emphasis small mb-1'}, icon('bi-exclamation-triangle', 'me-1'),
                'This group keeps its children under "sections" – they are not rendered; use the raw YAML editor to rename the key to "subsections".'));
        }
        return out;
    }
    if (type === 'table') {
        const cols = Array.isArray(sec.columns) ? sec.columns : [];
        const rows = Array.isArray(sec.rows) ? sec.rows.length : 0;
        if (cols.length && typeof cols[0] === 'string') {
            return [h('div', {class: 'text-muted small'}, icon('bi-lock', 'me-1'),
                `Legacy column format (${cols.join(', ')}) – edit in raw YAML.`)];
        }
        return [listEl(path.concat('columns'), 'column', 'Drop columns here', cols.map((c, i) => fieldRow(path.concat('columns', i), c, 'column'))),
            h('div', {class: 'text-muted small mt-1'}, `${rows} initial row${rows === 1 ? '' : 's'}`
                + (sec.allow_append_row ? ' · users can add rows' : '') + (sec.allow_delete_row ? ' · users can delete rows' : ''))];
    }
    if (type === 'checklist') {
        if ('step_groups' in sec) {
            const groups = Array.isArray(sec.step_groups) ? sec.step_groups : [];
            return [listEl(path.concat('step_groups'), 'group', 'Drop step groups here',
                groups.map((g, i) => groupCard(path.concat('step_groups', i), g)))];
        }
        // flat checklist: steps directly in the section; dropping a group converts it to step_groups
        return [h('div', {class: 'dz-list', dataset: {list: pathAttr(path.concat('step_groups')), kind: 'group'}},
            stepList(path.concat('steps'), sec.steps))];
    }
    if (Array.isArray(sec.fields) || type === 'header' || type === 'form') {
        const fields = Array.isArray(sec.fields) ? sec.fields : [];
        return [listEl(path.concat('fields'), 'field', 'Drop fields here', fields.map((f, i) => fieldRow(path.concat('fields', i), f, 'field')))];
    }
    return [h('div', {class: 'text-muted small'}, icon('bi-puzzle', 'me-1'),
        'Custom section type – its content is kept as is; edit it in the raw YAML editor.')];
}

function sectionCard(path, sec) {
    if (!M.isObject(sec)) return h('div', {class: 'dz-row dz-locked'}, icon('bi-lock', 'me-1'), 'Unsupported section – edit in raw YAML');
    const meta = sectionMeta(sec.type);
    return h('div', itemAttrs(path, 'dz-section'),
        h('div', {class: 'dz-section-head'}, icon('bi-grip-vertical', 'dz-handle'), icon(meta.icon, 'text-primary'),
            h('span', {class: 'fw-semibold'}, sec.title || h('em', {class: 'text-muted fw-normal'}, '(untitled)')),
            badge(meta.label),
            sec.id ? h('code', {class: 'dz-row-key'}, sec.id) : null,
            sec.always_expanded ? badge('always expanded') : null),
        h('div', {class: 'dz-section-body'}, sectionBody(path, sec)));
}

function inheritedBlock() {
    const inh = S.tpl.inherited;
    if (!S.tpl.model.extends) return null;
    if (!inh || inh.error) {
        return h('div', {class: 'alert alert-danger small py-2'}, icon('bi-exclamation-triangle', 'me-1'),
            (inh && inh.error) || 'Parent template could not be loaded.');
    }
    return h('div', {class: 'dz-inherited mb-2'},
        h('div', {class: 'small text-muted mb-1'}, icon('bi-diagram-2', 'me-1'),
            `Inherited from ${inh.chain.join(' → ')} (read-only, shown before this template's sections):`),
        inh.sections.filter(M.isObject).map(sec => h('div', {class: 'dz-inherited-item'},
            icon(sectionMeta(sec.type).icon, 'me-2'), sec.title || sec.id || '(untitled)',
            h('span', {class: 'text-muted ms-2'}, sectionMeta(sec.type).label))));
}

function renderCanvas() {
    const t = S.tpl;
    const canvas = $('dz-canvas');
    const scroll = window.scrollY;
    clear(canvas);
    const sections = Array.isArray(t.model.sections) ? t.model.sections : [];
    put(canvas,
        h('div', {class: 'dz-item dz-template-card', tabIndex: 0, dataset: {path: '[]'}},
            icon('bi-file-earmark-text', 'me-2 text-primary'),
            h('span', {class: 'fw-semibold'}, t.model.name || '(unnamed template)'),
            h('span', {class: 'text-muted small ms-2'}, 'template settings'),
            t.model.abstract ? h('span', {class: 'ms-2'}, badge('abstract')) : null,
            t.model.extends ? h('span', {class: 'ms-2'}, badge(`extends ${t.model.extends}`)) : null),
        inheritedBlock() || '',
        listEl(['sections'], 'section', 'Drag a section from the palette or click it to start', sections.map((s, i) => sectionCard(['sections', i], s))));
    highlightSelection();
    window.scrollTo(0, scroll);
}

function highlightSelection() {
    const want = pathAttr(S.tpl.sel || []);
    $('dz-canvas').querySelectorAll('[data-path]').forEach(el =>
        el.classList.toggle('dz-selected', el.dataset.path === want));
}

// ── Drag & drop on the canvas ──────────────────────────────────────────────

function endDrag() {
    drag = null;
    dropTarget = null;
    document.querySelectorAll('.dz-indicator').forEach(el => el.remove());
    document.querySelectorAll('.dz-dragging').forEach(el => el.classList.remove('dz-dragging'));
}

function acceptingList(startEl) {
    const model = S.tpl.model;
    const item = drag.src === 'canvas' ? M.get(model, drag.path) : {type: drag.type};
    let el = startEl.closest ? startEl.closest('.dz-list') : null;
    while (el) {
        const listPath = JSON.parse(el.dataset.list);
        const intoSelf = drag.src === 'canvas' && M.isPrefix(drag.path, listPath);
        if (!intoSelf && M.canDrop(model, drag.kind, listPath, item)) return el;
        el = el.parentElement ? el.parentElement.closest('.dz-list') : null;
    }
    return null;
}

function wireCanvas() {
    const canvas = $('dz-canvas');
    canvas.addEventListener('click', e => {
        const item = e.target.closest('[data-path]');
        if (item) select(JSON.parse(item.dataset.path));
    });
    canvas.addEventListener('keydown', e => {
        const item = e.target.closest('[data-path]');
        if (!item || e.target !== item) return;
        const path = JSON.parse(item.dataset.path);
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(path); }
        else if (e.key === 'Delete' && path.length) { e.preventDefault(); removeNode(path); }
    });
    canvas.addEventListener('dragstart', e => {
        const item = e.target.closest ? e.target.closest('.dz-item[draggable="true"]') : null;
        if (!item || !item.dataset.path || item.dataset.path === '[]') return;
        const path = JSON.parse(item.dataset.path);
        drag = {src: 'canvas', kind: M.kindOf(path), path};
        item.classList.add('dz-dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', item.dataset.path);
        e.stopPropagation();
    });
    canvas.addEventListener('dragover', e => {
        if (!drag) return;
        const list = acceptingList(e.target);
        document.querySelectorAll('.dz-indicator').forEach(el => el.remove());
        if (!list) { dropTarget = null; return; }
        e.preventDefault();
        e.dataTransfer.dropEffect = drag.src === 'palette' ? 'copy' : 'move';
        const items = Array.from(list.children).filter(c => c.classList.contains('dz-item'));
        let index = items.length;
        for (let i = 0; i < items.length; i++) {
            const rect = items[i].getBoundingClientRect();
            if (e.clientY < rect.top + rect.height / 2) { index = i; break; }
        }
        const indicator = h('div', {class: 'dz-indicator'});
        if (index < items.length) list.insertBefore(indicator, items[index]);
        else list.appendChild(indicator);
        dropTarget = {listPath: JSON.parse(list.dataset.list), index};
    });
    canvas.addEventListener('drop', e => {
        if (!drag || !dropTarget) { endDrag(); return; }
        e.preventDefault();
        const d = drag, target = dropTarget;
        endDrag();
        if (d.src === 'palette') {
            addItem(d.kind, d.type, target.listPath, target.index);
        } else {
            const model = S.tpl.model;
            const existed = Array.isArray(M.get(model, target.listPath));
            mutate(() => {
                const moved = M.move(model, d.path, target.listPath, existed ? target.index : null);
                if (moved) S.tpl.sel = moved;
            });
        }
    });
    canvas.addEventListener('dragend', endDrag);
}

// ── Node actions ───────────────────────────────────────────────────────────

function removeNode(path) {
    mutate(() => {
        M.remove(S.tpl.model, path);
        const kind = M.kindOf(path);
        S.tpl.sel = kind === 'section' ? [] : (M.sectionPathOf(path.slice(0, -2)) || []);
    });
}

function nodeActions(path) {
    const model = S.tpl.model;
    return h('div', {class: 'btn-group'},
        iconButton('bi-arrow-up', 'Move up', () => mutate(() => { S.tpl.sel = M.shift(model, path, -1); })),
        iconButton('bi-arrow-down', 'Move down', () => mutate(() => { S.tpl.sel = M.shift(model, path, 1); })),
        iconButton('bi-copy', 'Duplicate', () => mutate(() => { S.tpl.sel = M.duplicate(model, path) || path; })),
        iconButton('bi-trash', 'Delete', () => removeNode(path), 'btn-outline-danger'));
}

// ── Attribute panel ────────────────────────────────────────────────────────

let ctlSeq = 0;

/** Text control bound to a node attribute, with undo coalescing. */
function prop(node, key, opts) {
    const o = opts || {};
    const id = `c${++ctlSeq}`;
    return boundText(() => node, key, Object.assign({}, o, {
        before: () => pushUndo(id),
        after: (v, el) => { if (o.after) o.after(v, el); edited(el, !!o.rerender); },
    }));
}

function propCheck(label, checked, onChange, help, rerender) {
    return boundCheck(label, checked, v => { pushUndo(null); onChange(v); edited(null, rerender !== false); }, help);
}

function linesControl(getList, setList, placeholder, rows) {
    const id = `c${++ctlSeq}`;
    const ta = h('textarea', {class: 'form-control form-control-sm', rows: rows || 4, placeholder: placeholder || 'One item per line'});
    ta.value = (getList() || []).map(String).join('\n');
    ta.addEventListener('input', () => {
        pushUndo(id);
        setList(ta.value.split('\n').map(s => s.trim()).filter(Boolean));
        edited(ta, false);
    });
    return ta;
}

function otherAttributes(node, kind) {
    const keys = M.otherKeys(node, kind).filter(k => !(kind === 'section' && node.type === 'table' && k === 'hints'));
    if (!keys.length) return null;
    return h('div', {class: 'dz-other mt-3'},
        h('div', {class: 'small fw-semibold mb-1'}, icon('bi-shield-check', 'me-1'), 'Other attributes (kept as they are)'),
        keys.map(k => {
            let text = JSON.stringify(node[k]);
            if (text && text.length > 240) text = text.slice(0, 240) + '…';
            return h('div', {class: 'small'}, h('code', {}, k), ': ', h('span', {class: 'text-muted text-break'}, text));
        }),
        h('div', {class: 'form-text'}, 'The designer has no control for these – change them in the raw YAML editor.'));
}

function conditionControl(node, key, siblings) {
    const input = prop(node, key, {mono: true, placeholder: "field == 'value'", label: key});
    const others = siblings.filter(f => M.isObject(f) && f !== node && f.key);
    if (!others.length) return input;
    const valueInput = h('input', {type: 'text', class: 'form-control form-control-sm', placeholder: 'value', 'aria-label': 'Condition value', list: `dz-cond-${key}`});
    const dl = h('datalist', {id: `dz-cond-${key}`});
    const fill = () => {
        clear(dl);
        const ref = others.find(f => f.key === fieldSel.value);
        (ref && Array.isArray(ref.options) ? ref.options : []).forEach(o => dl.appendChild(h('option', {value: String(o)})));
    };
    const fieldSel = selectBox(others.map(f => ({value: f.key, label: f.label ? `${f.label} (${f.key})` : f.key})), others[0].key, fill, 'Condition field');
    const opSel = selectBox([{value: '==', label: 'is'}, {value: '!=', label: 'is not'}, {value: 'empty', label: 'is empty'},
        {value: 'filled', label: 'is filled'}], '==', v => valueInput.classList.toggle('d-none', v === 'empty' || v === 'filled'), 'Condition operator');
    fill();
    const builder = h('div', {class: 'dz-cond-builder mt-1'}, fieldSel, opSel, valueInput, dl,
        h('button', {type: 'button', class: 'btn btn-outline-secondary btn-sm', title: 'Write the condition', onclick: () => {
            pushUndo(null);
            M.setProp(node, key, M.buildCondition(fieldSel.value, opSel.value, valueInput.value));
            input.value = node[key] || '';
            edited(null, false);
        }}, 'Set'));
    return h('div', {}, input, builder);
}

function propsTemplate(panel) {
    const t = S.tpl, model = t.model;
    const idInput = prop(model, 'template_id', {mono: true, disabled: !t.isNew, label: 'Template id',
        write: (o, v) => { o.template_id = v.trim(); },
        after: v => {
            if (t.isNew && !t.fileTouched) t.filename = v.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '_').replace(/-/g, '_');
            if (fileInput) fileInput.value = t.filename;
        }});
    const fileInput = t.isNew ? h('input', {type: 'text', class: 'form-control form-control-sm font-monospace', value: t.filename,
        'aria-label': 'File name', oninput: () => { t.filename = fileInput.value.trim(); t.fileTouched = true; renderToolbar(); }}) : null;
    const parents = S.templates.filter(x => x.template_id && x.template_id !== model.template_id)
        .map(x => ({value: x.template_id, label: `${x.name || x.template_id}${x.abstract ? ' (abstract)' : ''}`}));
    put(panel,
        formRow('Name', prop(model, 'name', {write: (o, v) => { o.name = v; }, label: 'Template name'})),
        formRow('Template id', idInput, t.isNew ? 'Letters, digits, "-" and "_", e.g. helpdesk-request-v1. Cannot be changed later.'
            : 'The id cannot be changed – create a new template instead.'),
        fileInput ? formRow('File name', h('div', {class: 'input-group input-group-sm'}, fileInput, h('span', {class: 'input-group-text'}, '.yaml'))) : null,
        h('div', {class: 'row'},
            h('div', {class: 'col-6'}, formRow('Version', prop(model, 'version', {label: 'Version', placeholder: '1.0'}))),
            h('div', {class: 'col-6'}, formRow('Status', selectBox(S.catalog.template_statuses.map(s => ({value: s, label: s})),
                model.status || 'active', v => { pushUndo(null); model.status = v; edited(null, false); }, 'Status')))),
        formRow('Category', prop(model, 'category', {label: 'Category'})),
        formRow('Description', prop(model, 'description', {multiline: true, rows: 2, label: 'Description'})),
        formRow('Extends', selectBox([{value: '', label: '– none –'}].concat(parents), model.extends || '', v => {
            pushUndo(null); M.setProp(model, 'extends', v); edited(null, false);
        }, 'Parent template'), 'Sections of the parent are placed before the sections of this template.'),
        propCheck('Abstract template', !!model.abstract, v => M.setBool(model, 'abstract', v, false),
            'Only a base for other templates – records cannot be created from it.'));

    // meta
    const meta = M.isObject(model.meta) ? model.meta : null;
    const metaBox = h('div', {});
    Object.keys(meta || {}).forEach(k => {
        const simple = meta[k] === null || ['string', 'number', 'boolean'].includes(typeof meta[k]);
        metaBox.appendChild(h('div', {class: 'input-group input-group-sm mb-1'},
            h('span', {class: 'input-group-text font-monospace'}, k),
            simple ? prop(meta, k, {label: `meta ${k}`, keepNull: true})
                   : h('input', {type: 'text', class: 'form-control', disabled: true, value: JSON.stringify(meta[k])}),
            iconButton('bi-x', 'Remove', () => mutate(() => { delete meta[k]; if (!Object.keys(meta).length) delete model.meta; }))));
    });
    const newKey = h('input', {type: 'text', class: 'form-control font-monospace', placeholder: 'new key', 'aria-label': 'New meta key'});
    put(panel, formRow('Meta values', h('div', {}, metaBox, h('div', {class: 'input-group input-group-sm'}, newKey,
        h('button', {type: 'button', class: 'btn btn-outline-secondary', onclick: () => {
            const k = newKey.value.trim();
            if (!/^[A-Za-z_][\w-]*$/.test(k) || (meta && k in meta)) { showToast('Enter a new key (letters, digits, "_")', 'warning'); return; }
            mutate(() => { ensureObj(model, 'meta')[k] = ''; });
        }}, 'Add'))), 'Available to automatic fields as meta.<key>.'),
        otherAttributes(model, 'template') || '');
}

function propsSection(panel, path, sec) {
    const nested = path.length > 2;
    const meta = sectionMeta(sec.type);
    put(panel,
        formRow('Title', prop(sec, 'title', {label: 'Section title'})),
        formRow('Id', prop(sec, 'id', {mono: true, label: 'Section id', placeholder: M.slugify(sec.title || sec.type || 'section')}),
            'Empty = generated from the title.'),
        formRow('Type', h('div', {}, badge(meta.label), ' ', h('span', {class: 'form-text'}, meta.description || ''))));
    if (sec.type !== 'section_group') {
        put(panel, formRow('Description', prop(sec, 'description', {label: 'Description'}), 'Short text next to the title.'));
    }
    if (['header', 'form', 'table'].includes(sec.type)) {
        put(panel, formRow('Hint', prop(sec, 'hint', {multiline: true, rows: 2, label: 'Hint'}), 'Info box above the section content.'));
    }
    if (nested) {
        put(panel, formRow('Note', prop(sec, 'note', {label: 'Note'}), 'Small text next to the accordion title.'),
            propCheck('Always expanded', !!sec.always_expanded, v => M.setBool(sec, 'always_expanded', v, false), 'The sub-section cannot be collapsed.'));
    }
    if (sec.type === 'table') propsTable(panel, sec);
    put(panel, otherAttributes(sec, 'section') || '');
}

function propsTable(panel, sec) {
    const cols = (Array.isArray(sec.columns) ? sec.columns : []).filter(M.isObject);
    put(panel,
        propCheck('Users can add rows', !!sec.allow_append_row, v => M.setBool(sec, 'allow_append_row', v, false), null, false),
        propCheck('Users can delete rows', !!sec.allow_delete_row, v => M.setBool(sec, 'allow_delete_row', v, false), null, false),
        formRow('Notes under the table', linesControl(() => (Array.isArray(sec.hints) ? sec.hints : []), list => M.setProp(sec, 'hints', list), 'One note per line', 2)));
    if (!cols.length) return;
    const cell = (obj, col, onEmpty) => {
        const id = `c${++ctlSeq}`;
        const value = obj[col.key];
        const input = h('input', {type: 'text', class: 'form-control form-control-sm', placeholder: col.label || col.key,
            'aria-label': col.label || col.key, value: value === null || value === undefined ? '' : String(value)});
        input.addEventListener('input', () => { pushUndo(id); onEmpty(input.value); edited(input, false); });
        return input;
    };
    // defaults for rows added by the user
    const tplBox = h('div', {});
    cols.forEach(col => tplBox.appendChild(h('div', {class: 'input-group input-group-sm mb-1'},
        h('span', {class: 'input-group-text dz-term-key'}, col.label || col.key),
        cell(M.isObject(sec.append_row_template) ? sec.append_row_template : {}, col, v => {
            const target = ensureObj(sec, 'append_row_template');
            M.setProp(target, col.key, v);
            if (!Object.keys(target).length) delete sec.append_row_template;
        }))));
    put(panel, formRow('Default values of a new row', tplBox, 'Used when a user adds a row.'));
    // initial rows
    const rows = Array.isArray(sec.rows) ? sec.rows : [];
    const rowsBox = h('div', {});
    rows.forEach((row, ri) => {
        if (!M.isObject(row)) return;
        rowsBox.appendChild(h('div', {class: 'dz-rowcard'},
            h('div', {class: 'd-flex justify-content-between align-items-center mb-1'}, h('span', {class: 'small text-muted'}, `Row ${ri + 1}`),
                iconButton('bi-x', 'Remove row', () => mutate(() => { rows.splice(ri, 1); }))),
            cols.map(col => h('div', {class: 'mb-1'}, cell(row, col, v => { row[col.key] = v === '' ? null : v; })))));
    });
    put(panel, formRow(`Initial rows (${rows.length})`, h('div', {}, rowsBox,
        h('button', {type: 'button', class: 'btn btn-outline-secondary btn-sm', onclick: () => mutate(() => {
            if (!Array.isArray(sec.rows)) sec.rows = [];
            const row = {};
            cols.forEach(c => { row[c.key] = null; });
            sec.rows.push(row);
        })}, icon('bi-plus', 'me-1'), 'Add row')), 'Rows every new record starts with.'));
}

function propsField(panel, path, field, kind) {
    const isCol = kind === 'column';
    const siblings = M.get(S.tpl.model, path.slice(0, -1)) || [];
    const auto = isCol ? '' : M.getAuto(field);
    const types = isCol ? S.catalog.column_types.map(t => ({value: t, label: t}))
                        : S.catalog.field_types.map(t => ({value: t.type, label: t.label}));
    put(panel,
        formRow('Label', prop(field, 'label', {label: 'Label'})),
        formRow('Key', prop(field, 'key', {mono: true, label: 'Key', write: (o, v) => { o.key = v.trim(); }}),
            isCol ? 'Key of the value in a table row.' : 'Unique in the section; used by list columns, conditions and exports.'),
        formRow('Type', selectBox(types, field.type || 'text', v => {
            pushUndo(null);
            if (v === 'text' && !('type' in field)) { /* default – nothing to write */ } else field.type = v;
            if (v === 'select' && !Array.isArray(field.options)) field.options = [];
            edited(null, true);
        }, 'Type')));
    if ((field.type || 'text') === 'select') {
        put(panel, formRow('Options', linesControl(() => field.options, list => { field.options = list; }, 'One option per line', 5),
            'The whole option text is stored as the value.'));
    }
    if (isCol) {
        put(panel, propCheck('Editable', field.editable === true, v => M.setBool(field, 'editable', v, false),
            'Read-only columns show the text from the template rows.', false),
            otherAttributes(field, 'column') || '');
        return;
    }
    const sources = [{value: '', label: '– none (user fills it in) –'}].concat(S.catalog.auto_sources)
        .concat(Object.keys(M.isObject(S.tpl.model.meta) ? S.tpl.model.meta : {}).map(k => ({value: `meta.${k}`, label: `Template meta: ${k}`})));
    put(panel, formRow('Automatic value', selectBox(sources, auto, v => { pushUndo(null); M.setAuto(field, v); edited(null, true); }, 'Automatic value'),
        'Automatic fields are filled by the system and are read-only.'));
    if (!auto) {
        put(panel,
            propCheck('Editable', field.editable !== false, v => M.setBool(field, 'editable', v, true), null, false),
            propCheck('Required', !!field.required, v => M.setBool(field, 'required', v, false), 'Marks the field as mandatory.', false),
            formRow('Placeholder', prop(field, 'placeholder', {label: 'Placeholder'}), 'Hint inside the empty input.'),
            formRow('Example', prop(field, 'example', {multiline: field.type === 'textarea', rows: 2, label: 'Example'}),
                'Sample of a well filled value, shown in grey until the user types.'),
            formRow('Default value', prop(field, 'value', {label: 'Default value', keepNull: true,
                write: (o, v) => {
                    const num = field.type === 'number' && v.trim() !== '' && Number.isFinite(Number(v)) ? Number(v) : null;
                    M.setProp(o, 'value', num !== null ? num : v, {keepNull: true});
                }})));
    }
    put(panel,
        formRow('Hint', prop(field, 'hint', {label: 'Hint'}), 'Grey text under the input.'),
        formRow('Visible if', conditionControl(field, 'visible_if', siblings), 'Show the field only when the condition holds (fields of the same section).'),
        formRow('Required if', conditionControl(field, 'required_if', siblings)),
        otherAttributes(field, 'field') || '');
}

function propsGroup(panel, group) {
    put(panel,
        formRow('Title', prop(group, 'title', {label: 'Group title', keepNull: true}), 'Empty = steps without a heading.'),
        formRow('Id', prop(group, 'id', {mono: true, label: 'Group id', placeholder: M.slugify(group.title || 'group')}), 'Empty = generated from the title.'),
        formRow('Note', prop(group, 'note', {label: 'Note'}), 'Small text next to the title, e.g. a time target.'),
        formRow('Hints', linesControl(() => (Array.isArray(group.hints) ? group.hints : []), list => M.setProp(group, 'hints', list), 'One hint per line', 3)),
        otherAttributes(group, 'group') || '');
}

function propsStep(panel, path) {
    const steps = M.get(S.tpl.model, path.slice(0, -1));
    const index = path[path.length - 1];
    const cur = () => steps[index];
    const val = key => (M.isObject(cur()) && cur()[key] != null && typeof cur()[key] !== 'object' ? String(cur()[key]) : '');
    const stepText = (key, multiline, placeholder) => {
        const id = `c${++ctlSeq}`;
        const el = h(multiline ? 'textarea' : 'input', {class: 'form-control form-control-sm', placeholder: placeholder || '', 'aria-label': key});
        if (multiline) el.rows = 3; else el.type = 'text';
        el.value = key === 'action' ? M.stepAction(cur()) : val(key);
        el.addEventListener('input', () => { pushUndo(id); M.setStepProp(steps, index, key, el.value); edited(el, false); });
        return el;
    };
    const hintIsList = M.isObject(cur()) && Array.isArray(cur().hint);
    put(panel,
        formRow('Step', stepText('action', true, 'What should be done'), 'Instruction shown next to the checkbox.'),
        hintIsList
            ? formRow('Hint', h('div', {class: 'small text-muted'}, `${cur().hint.length} hint lines – kept as they are (edit in raw YAML).`))
            : formRow('Hint', stepText('hint', false), 'Note shown under the step.'),
        formRow('Example note', stepText('example', true), 'Sample text for the note of the person doing the step.'),
        formRow('Id', stepText('id', false, 'generated'), 'Empty = generated from the position.'),
        M.isObject(cur()) ? otherAttributes(cur(), 'step') : null);
}

function renderProps() {
    const t = S.tpl;
    const panel = clear($('dz-props'));
    const path = t.sel || [];
    const kind = M.kindOf(path);
    const node = M.get(t.model, path);
    if (node === undefined || !kind) { t.sel = []; return renderProps(); }
    put(panel, h('div', {class: 'd-flex justify-content-between align-items-center mb-3'},
        h('h6', {class: 'fw-bold mb-0'}, KIND_LABELS[kind] || kind),
        path.length ? nodeActions(path) : null));
    if (kind === 'template') propsTemplate(panel);
    else if (kind === 'section' && M.isObject(node)) propsSection(panel, path, node);
    else if ((kind === 'field' || kind === 'column') && M.isObject(node)) propsField(panel, path, node, kind);
    else if (kind === 'group' && M.isObject(node)) propsGroup(panel, node);
    else if (kind === 'step') propsStep(panel, path);
}

// ── Server check: validation, preview, YAML ────────────────────────────────

function scheduleCheck(delay) {
    clearTimeout(checkTimer);
    checkTimer = setTimeout(runCheck, delay === undefined ? 500 : delay);
}

async function runCheck() {
    const t = S.tpl;
    if (!t) return;
    const seq = ++checkSeq;
    const r = await api('POST', `${colUrl()}/check-template`, {model: t.model});
    if (seq !== checkSeq || S.tpl !== t) return;       // a newer check is on its way
    if (!r.ok) {
        t.check = {ok: false, yaml: '', sections: [], issues: [{level: 'error', path: '', message: errInfo(r).message}]};
    } else {
        t.check = r.data;
        const before = JSON.stringify(t.inherited);
        t.inherited = r.data.inherited;
        if (JSON.stringify(t.inherited) !== before) renderCanvas();
    }
    renderCheckResult();
}

function renderCheckResult() {
    const t = S.tpl;
    if (!t) return;
    const check = t.check;
    const issuesBox = clear($('dz-issues'));
    if (!check) {
        put(issuesBox, h('span', {class: 'text-muted small'}, 'Checking…'));
    } else {
        const errors = check.issues.filter(i => i.level === 'error').length;
        const warnings = check.issues.length - errors;
        put(issuesBox, h('div', {class: 'small fw-semibold mb-1'},
            errors ? h('span', {class: 'text-danger me-2'}, `${errors} error${errors === 1 ? '' : 's'}`) : null,
            warnings ? h('span', {class: 'text-warning-emphasis me-2'}, `${warnings} warning${warnings === 1 ? '' : 's'}`) : null,
            !check.issues.length ? h('span', {class: 'text-success'}, icon('bi-check-circle', 'me-1'), 'Template is valid') : null),
            issuesList(check.issues) || '');
    }
    const previewVisible = !$('dz-preview-wrap').classList.contains('d-none');
    if (previewVisible) {
        const box = $('dz-preview');
        if (!check) { put(clear(box), h('div', {class: 'text-muted small'}, 'Loading preview…')); }
        else if (!check.ok) { put(clear(box), h('div', {class: 'alert alert-warning small py-2'}, 'Fix the errors to see the preview.')); }
        else {
            try {
                // UniForms.render writes user input back into the objects – always give it a copy
                UniForms.render(M.clone(check.sections), box);
                if (!check.sections.length) put(box, h('div', {class: 'dz-empty'}, 'The template has no sections yet.'));
            } catch (err) {
                put(clear(box), h('div', {class: 'alert alert-danger small py-2'}, `Preview failed: ${err.message}`));
            }
        }
    }
    if (t.view === 'yaml') $('dz-yaml').textContent = check ? (check.yaml || '(not available – fix the errors first)') : 'Loading…';
}

async function saveTemplate() {
    const t = S.tpl;
    const btn = $('dz-tpl-save');
    if (t.isNew && !SLUG_RE.test(t.filename)) {
        showToast('File name may only contain lowercase letters, digits, "-" and "_"', 'danger');
        select([]);
        return;
    }
    btn.disabled = true;
    const r = await saveFlow(confirm => (t.isNew
        ? api('POST', `${colUrl()}/templates`, {filename: t.filename, model: t.model})
        : api('PUT', `${colUrl()}/templates/${encodeURIComponent(t.templateId)}`,
              {model: t.model, base_hash: t.source ? t.source.hash : null, confirm_rewrite: confirm})));
    if (S.tpl !== t) return;
    if (!r) { renderToolbar(); return; }
    if (!r.ok) {
        const e = errInfo(r);
        showAlert('dz-tpl-alert', 'danger', h('div', {class: 'fw-semibold'}, e.message), issuesList(e.issues) || '',
            e.code === 'stale' ? h('div', {class: 'mt-1'}, 'Close the template and open it again to load the current file.') : '');
        renderToolbar();
        return;
    }
    showAlert('dz-tpl-alert', null);
    const wasNew = t.isNew;
    t.isNew = false;
    t.templateId = r.data.template_id;
    t.filename = r.data.filename;
    t.source = r.data.source;
    t.saved = JSON.stringify(t.model);
    showToast(r.data.change === 'unchanged' ? 'Nothing to save – file unchanged' : (wasNew ? 'Template created' : 'Template saved'));
    await refreshTemplates();
    renderToolbar();
    if (wasNew) renderProps();
}

function wireTemplateView() {
    $('dz-tpl-back').addEventListener('click', closeTemplate);
    $('dz-tpl-undo').addEventListener('click', undo);
    $('dz-tpl-save').addEventListener('click', saveTemplate);
    document.querySelectorAll('#dz-tpl-tabs [data-view]').forEach(btn => btn.addEventListener('click', () => {
        S.tpl.view = btn.dataset.view;
        applyView();
    }));
    $('dz-live-toggle').addEventListener('change', e => { S.tpl.live = e.target.checked; applyView(); });
    wireCanvas();
}

// ───────────────────────────────────────────────────────────────────────────
// Boot
// ───────────────────────────────────────────────────────────────────────────

async function init() {
    const cat = await api('GET', `${API}/catalog`);
    if (!cat.ok) { showAlert('dz-alert', 'danger', errInfo(cat).message); return; }
    S.catalog = cat.data;

    if (S.mode === 'edit') {
        const r = await api('GET', colUrl());
        if (!r.ok) {
            showAlert('dz-alert', 'danger', errInfo(r).message, ' ',
                h('a', {href: `/admin/collections/${encodeURIComponent(S.cid)}/edit`}, 'Open the raw YAML editor'));
            $('dz-loading').classList.add('d-none');
            return;
        }
        S.model = r.data.model;
        S.source = r.data.source;
        S.templates = r.data.templates || [];
        S.fieldKeys = r.data.field_keys || [];
    } else {
        S.model = M.clone(S.catalog.defaults.collection);
    }
    S.saved = JSON.stringify(S.model);

    $('dz-prev').addEventListener('click', () => {
        let i = S.step - 1;
        if (STEPS[i] && STEPS[i].id === 'templates' && S.mode === 'new') i -= 1;
        goStep(i);
    });
    $('dz-next').addEventListener('click', () => goStep(S.step + 1));
    wireNewTemplateDialog();
    wireTemplateView();
    window.addEventListener('beforeunload', e => {
        if (colDirty() || (S.tpl && tplDirty())) { e.preventDefault(); e.returnValue = ''; }
    });

    $('dz-loading').classList.add('d-none');
    $('dz-collection-view').classList.remove('d-none');
    colChanged();
    const hash = (window.location.hash || '').slice(1);
    const wanted = STEPS.findIndex(s => s.id === hash);
    goStep(wanted >= 0 ? wanted : 0);
    // deep link from the template list: #template=<template_id> opens that template directly
    if (S.mode === 'edit' && hash.startsWith('template=')) {
        let templateId = '';
        try { templateId = decodeURIComponent(hash.slice('template='.length)); } catch (err) { templateId = ''; }
        if (S.templates.some(t => t.template_id === templateId && t.loadable)) await openTemplate(templateId);
        else goStep(STEPS.findIndex(s => s.id === 'templates'));
    }
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
else init();
})();
