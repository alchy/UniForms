/**
 * UniForms – dynamic JSON document renderer
 *
 * ARCHITECTURE:
 *
 * This file is the "view layer" for the record detail page.
 * Instead of server-side Jinja2 rendering, all form rendering happens
 * in the browser from JSON data.
 *
 * Data flow:
 *   1. Backend returns the record JSON via REST API
 *   2. renderSections() iterates sections and dispatches each to the
 *      appropriate render* function by section.type
 *   3. render* functions build DOM elements and return them
 *   4. User edits a field → change is immediately written back to the
 *      JS object (field.value = inp.value) – the object is always current
 *   5. On Save: the JS object is serialized to JSON and sent to the backend
 *
 * Extension points:
 *   UniForms.render(sections, container)           – render a form
 *   UniForms.registerRenderer(type, fn)            – register a custom section type
 *
 * Section types:
 *   header        – read-only info grid + editable fields in a card header
 *   form          – editable form fields in a card body
 *   table         – editable table with per-column type/options/editable flags
 *   checklist     – step groups with checkboxes and analyst notes
 *   section_group – accordion container wrapping subsections
 *
 * Template schema features:
 *   - auto: <source> fields (resolved by backend; rendered read-only)
 *   - visible_if: "field == 'value'"  (conditional field visibility)
 *   - required_if: "field == 'value'" (conditional required indicator)
 *   - placeholder: "..."              (UI hint, not saved as value)
 *   - flat steps: (resolved by backend into step_groups with null title)
 *   - append_row_template: {}         (default values for user-added table rows)
 *   - type: datetime, display_tz: local|utc  (stored as UTC '…Z'; shown/entered in the
 *                                      app timezone APP_TIME.timezone, or in UTC)
 *   - type: date ('YYYY-MM-DD') / time ('HH:MM', local wall-clock, e.g. a feeding
 *     schedule) – stored as typed, never converted between time zones
 *   - table columns may use the same types: date, time, datetime
 *   - type: user, source: <src>       (app-defined list: users of the collection;
 *                                      needs UniForms.setUserProvider, else a text input)
 */

const UniForms = (() => {

// ---------------------------------------------------------------------------
// HTML Sanitization – XSS protection
//
// Template content (titles, labels, hints) is inserted into the DOM via
// innerHTML. To prevent script injection from template JSON, all HTML passes
// through DOMParser in an isolated document before insertion.
// ---------------------------------------------------------------------------

function sanitizeHTML(html) {
    const doc = new DOMParser().parseFromString(String(html), 'text/html');
    doc.querySelectorAll('script, iframe, object, embed, link, meta').forEach(e => e.remove());
    doc.querySelectorAll('*').forEach(e => {
        [...e.attributes].forEach(a => {
            if (/^on/i.test(a.name)) e.removeAttribute(a.name);
            if (a.name === 'href' && /^javascript:/i.test(a.value)) e.removeAttribute(a.name);
        });
    });
    return doc.body.innerHTML;
}

function setHTML(element, html) {
    element.innerHTML = sanitizeHTML(html);
}

// ---------------------------------------------------------------------------
// Conditional expression evaluator
//
// Evaluates simple boolean expressions for visible_if / required_if.
//
// Supported syntax:
//   field_key == 'value'
//   field_key != 'value'
//   field_key == null    (true when field is empty/null)
//   field_key != null    (true when field has a value)
//   expr1 && expr2       (AND, higher precedence)
//   expr1 || expr2       (OR, lower precedence)
//
// Example: "priority == 'High' || priority == 'Critical'"
// ---------------------------------------------------------------------------

function evalExpr(expr, fields) {
    if (!expr) return true;
    const values = {};
    fields.forEach(f => { values[f.key] = f.value; });

    const evalAtom = (atom) => {
        atom = atom.trim();
        let m = atom.match(/^(\w+)\s*==\s*'([^']*)'$/);
        if (m) return values[m[1]] === m[2];
        m = atom.match(/^(\w+)\s*!=\s*'([^']*)'$/);
        if (m) return values[m[1]] !== m[2];
        m = atom.match(/^(\w+)\s*==\s*null$/);
        if (m) return !values[m[1]];
        m = atom.match(/^(\w+)\s*!=\s*null$/);
        if (m) return !!values[m[1]];
        return false;
    };

    // || has lowest precedence; && is higher
    return expr.split('||').some(orPart =>
        orPart.split('&&').every(atom => evalAtom(atom))
    );
}

// ---------------------------------------------------------------------------
// Conditional visibility / required
//
// Scans field rows in `container` for visible_if / required_if and
// updates their display after any change event in the container.
// ---------------------------------------------------------------------------

function applyConditionals(fields, container) {
    const hasConditionals = fields.some(f => f.visible_if !== undefined || f.required_if !== undefined);
    if (!hasConditionals) return;

    // Build key → row element map using data-key set by renderFieldRow
    const rowMap = new Map();
    container.querySelectorAll('.field-row').forEach(row => {
        rowMap.set(row.dataset.key, row);
    });

    function refresh() {
        fields.forEach(field => {
            const row = rowMap.get(field.key);
            if (!row) return;

            if (field.visible_if !== undefined) {
                row.style.display = evalExpr(field.visible_if, fields) ? '' : 'none';
            }

            if (field.required_if !== undefined) {
                const label = row.querySelector('label');
                if (label) {
                    const required = evalExpr(field.required_if, fields);
                    let star = label.querySelector('.required-star');
                    if (required && !star) {
                        label.insertAdjacentHTML('beforeend',
                            ' <span class="required-star text-danger" aria-hidden="true">*</span>');
                    } else if (!required && star) {
                        star.remove();
                    }
                }
            }
        });
    }

    container.addEventListener('change', refresh);
    refresh();
}

// ---------------------------------------------------------------------------
// Section renderer registry
//
// Maps section.type → render function.
// Extensions register additional types via UniForms.registerRenderer(type, fn).
// ---------------------------------------------------------------------------

const renderers = {
    header:        renderHeader,
    form:          renderFormSection,
    table:         renderTable,
    checklist:     renderChecklist,
    section_group: renderSectionGroup,
};

function renderSections(sections, container) {
    container.innerHTML = '';
    sections.forEach(section => {
        const el = renderSection(section);
        if (el) container.appendChild(el);
    });
}

function renderSection(section) {
    const wrapper = document.createElement('div');
    wrapper.className = 'case-section card border shadow-sm mb-3';
    wrapper.id = `sec-${section.id}`;

    const header = document.createElement('div');
    header.className = 'card-header d-flex align-items-center justify-content-between';
    setHTML(header, `
        <span class="fw-semibold">${section.title}</span>
        ${section.description ? `<small class="text-muted ms-3 d-none d-md-block" style="max-width:60%">${section.description}</small>` : ''}
    `);
    wrapper.appendChild(header);

    const body = document.createElement('div');
    body.className = 'card-body';

    const renderFn = renderers[section.type];
    if (renderFn) {
        body.appendChild(renderFn(section));
    } else {
        // Unknown section type – show raw JSON for debugging
        const pre = el('pre', 'text-secondary small mb-0');
        pre.textContent = JSON.stringify(section, null, 2);
        body.appendChild(pre);
    }

    wrapper.appendChild(body);
    return wrapper;
}

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------

function el(tag, cls, html) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html !== undefined) e.innerHTML = sanitizeHTML(html);
    return e;
}

function buildTableHead(columns, columnLabels, extraCol = false) {
    const thead = document.createElement('thead');
    const tr = document.createElement('tr');
    tr.className = 'table-light';
    columns.forEach(col => tr.appendChild(el('th', 'text-muted small', columnLabels?.[col] || col)));
    if (extraCol) tr.appendChild(el('th', 'text-muted small', ''));
    thead.appendChild(tr);
    return thead;
}

function makeDeleteBtn(onClick) {
    const btn = el('button', 'btn btn-link btn-sm text-danger p-0', '<i class="bi bi-trash"></i>');
    btn.addEventListener('click', onClick);
    return btn;
}

/**
 * Render a label + input row for a single field.
 * Adds class 'field-row' and data-key for conditional visibility.
 */
function renderFieldRow(field, labelCls = 'form-label text-secondary small mb-0', rowMb = 'mb-2') {
    const row = el('div', `row field-row ${rowMb} align-items-center`);
    row.dataset.key = field.key;

    const labelCol = el('div', 'col-md-4');
    const hintHtml = field.hint
        ? `<div class="form-text text-secondary" style="font-size:0.75rem">${field.hint}</div>` : '';
    setHTML(labelCol, `<label class="${labelCls}">${field.label}</label>${hintHtml}`);

    const inputCol = el('div', 'col-md-8');
    inputCol.appendChild(renderFieldInput(field));
    row.appendChild(labelCol);
    row.appendChild(inputCol);
    return row;
}

function renderInfoGrid(fields, colCls = 'col-md-4 col-lg-3', gridCls = 'row g-2') {
    const grid = el('div', gridCls);
    fields.forEach(field => {
        const col = el('div', colCls);
        setHTML(col, `<div class="d-flex flex-column">
            <span class="text-muted small">${field.label}</span>
            <span class="small fw-semibold uf-val"></span>
        </div>`);
        // value as text (never HTML); instants converted to the field's zone
        const valEl = col.querySelector('.uf-val');
        valEl.textContent = readonlyText(field);
        const d = isInstantField(field) ? parseInstant(field.value) : null;
        if (d) {
            valEl.title = `stored ${field.value}`;
            const z = el('span', 'text-muted small');
            z.textContent = zoneLabel(fieldZone(field), d);
            col.firstElementChild.appendChild(z);
        }
        grid.appendChild(col);
    });
    return grid;
}

function buildOptions(sel, options, currentValue) {
    options.forEach(opt => {
        const o = document.createElement('option');
        o.value = opt;
        o.textContent = opt;
        if (currentValue === opt) o.selected = true;
        sel.appendChild(o);
    });
}

// ---------------------------------------------------------------------------
// Date & time – instants are stored in UTC ('YYYY-MM-DDTHH:MM:SSZ') and shown /
// entered in the app timezone (APP_TIME.timezone) or in UTC (field.display_tz: utc).
// Legacy values without an offset were written in the .env zone (APP_TIME.legacy_timezone).
// ---------------------------------------------------------------------------

const APP_TIME_CFG = (typeof APP_TIME !== 'undefined' && APP_TIME) || {};
const APP_TZ = APP_TIME_CFG.timezone || 'UTC';
const DATE_FMT = APP_TIME_CFG.date_format || 'DD.MM.YYYY';     // Settings → Date & time
// Values saved before UTC storage have no offset; they were written in the .env zone,
// so they are read in that fixed zone – changing the Settings zone must not move them.
const LEGACY_TZ = APP_TIME_CFG.legacy_timezone || APP_TZ;
const TIME_12H = APP_TIME_CFG.time_format === '12h';
const AUTO_INSTANTS = ['now', 'last_saved'];

function isInstantField(field) {
    return field.type === 'datetime' || AUTO_INSTANTS.includes(field.auto_value);
}

function fieldZone(field) {
    return field.display_tz === 'utc' ? 'UTC' : APP_TZ;
}

// Wall-clock parts of a Date in an IANA zone
function zoneParts(date, tz) {
    const parts = {};
    new Intl.DateTimeFormat('en-US', {timeZone: tz, hourCycle: 'h23', year: 'numeric', month: '2-digit',
        day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit'})
        .formatToParts(date).forEach(p => { parts[p.type] = p.value; });
    return parts;
}

// Offset of the zone from UTC at that instant, in minutes (e.g. +120 for CEST)
function zoneOffset(date, tz) {
    const p = zoneParts(date, tz);
    const asUtc = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour % 24, +p.minute, +p.second);
    return Math.round((asUtc - Math.floor(date.getTime() / 1000) * 1000) / 60000);
}

// 'YYYY-MM-DDTHH:MM' wall time in a zone → Date (handles DST)
function wallToDate(wall, tz) {
    const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?$/.exec(wall || '');
    if (!m) return null;
    const guess = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0));
    let t = guess - zoneOffset(new Date(guess), tz) * 60000;
    t = guess - zoneOffset(new Date(t), tz) * 60000;
    return new Date(t);
}

// Stored value → Date (null when not a date-time)
function parseInstant(value) {
    if (typeof value !== 'string' || !value) return null;
    if (/(Z|[+-]\d{2}:?\d{2})$/.test(value)) {
        const d = new Date(value);
        return isNaN(d) ? null : d;
    }
    return wallToDate(value, LEGACY_TZ);       // legacy: local time of the .env zone
}

function pad2(n) { return String(n).padStart(2, '0'); }

function offsetText(date, tz) {
    const off = zoneOffset(date, tz), sign = off < 0 ? '-' : '+', a = Math.abs(off);
    return `UTC${sign}${pad2(Math.floor(a / 60))}:${pad2(a % 60)}`;
}

// Label of the zone a value is shown in, e.g. "Europe/Prague (UTC+02:00)" or "UTC"
function zoneLabel(tz, date) {
    return tz === 'UTC' ? 'UTC' : `${tz} (${offsetText(date || new Date(), tz)})`;
}

// Display text per Settings, e.g. "13.10.2026 11:04" or "2026-10-13 11:04 AM"
function formatInstant(value, tz) {
    const d = parseInstant(value);
    if (!d) return value;
    const p = zoneParts(d, tz || APP_TZ);
    const date = DATE_FMT.replace('DD', p.day).replace('MM', p.month).replace('YYYY', p.year);
    let time = `${p.hour}:${p.minute}`;
    if (TIME_12H) {
        const h = +p.hour;
        time = `${h % 12 || 12}:${p.minute} ${h < 12 ? 'AM' : 'PM'}`;
    }
    return `${date} ${time}`;
}

// Calendar day 'YYYY-MM-DD' and wall-clock time 'HH:MM' – no time zone involved
const DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;
const TIME_RE = /^(\d{2}):(\d{2})(?::\d{2})?$/;

function formatDate(value) {
    const m = DATE_RE.exec(value || '');
    return m ? DATE_FMT.replace('DD', m[3]).replace('MM', m[2]).replace('YYYY', m[1]) : value;
}

function formatTime(value) {
    const m = TIME_RE.exec(value || '');
    if (!m) return value;
    if (!TIME_12H) return `${m[1]}:${m[2]}`;
    const h = +m[1];
    return `${h % 12 || 12}:${m[2]} ${h < 12 ? 'AM' : 'PM'}`;
}

const LOCAL_TIME_NOTE = 'Local time – not converted between time zones';

// Display text of a typed value (field or table cell)
function formatTyped(type, value, tz) {
    if (value === null || value === undefined || value === '') return '–';
    if (type === 'date') return formatDate(value);
    if (type === 'time') return formatTime(value);
    if (type === 'datetime') {
        if (!parseInstant(value)) return value;
        return `${formatInstant(value, tz)}${tz === 'UTC' ? ' UTC' : ''}`;
    }
    return value;
}

// Date & time input bound to obj[key]: shows the value in `tz`, stores UTC '…Z'
function datetimeInput(obj, key, tz, cls, onChange) {
    const inp = el('input', cls || 'form-control form-control-sm');
    inp.type = 'datetime-local';
    const current = parseInstant(obj[key]);
    if (current) {
        const p = zoneParts(current, tz);
        inp.value = `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
    }
    inp.addEventListener('change', () => {
        const d = inp.value ? wallToDate(inp.value, tz) : null;
        obj[key] = d ? d.toISOString().replace(/\.\d{3}Z$/, 'Z') : null;
        if (onChange) onChange();
    });
    return inp;
}

// Date or time input bound to obj[key]; the value is stored exactly as typed
function plainInput(type, obj, key, cls) {
    const inp = el('input', cls || 'form-control form-control-sm');
    const v = obj[key];
    const fmt = type === 'date' ? 'YYYY-MM-DD' : 'HH:MM';
    if (v && !(type === 'date' ? DATE_RE : TIME_RE).test(v)) {
        // older free text (e.g. "ráno") – keep it visible and editable; saved unchanged it stays as is
        inp.type = 'text';
        inp.value = v;
        inp.placeholder = fmt;
        inp.title = `Older value – to change it, enter ${fmt}`;
        inp.classList.add('uf-legacy-value');
    } else {
        inp.type = type;                   // 'date' | 'time'
        if (type === 'time') inp.step = 60;
        if (v) inp.value = type === 'time' ? v.slice(0, 5) : v;
    }
    inp.addEventListener('change', () => { obj[key] = inp.value || null; });
    return inp;
}

function renderDatetimeInput(field) {
    const tz = fieldZone(field);
    const wrap = el('div');
    const note = el('div', 'form-text text-secondary small mt-1 uf-tz-note');
    const showNote = () => { note.textContent = `Time zone: ${zoneLabel(tz, parseInstant(field.value))}`; };
    const inp = datetimeInput(field, 'value', tz, null, showNote);
    inp.dataset.fieldKey = field.key;
    showNote();
    wrap.appendChild(inp);
    wrap.appendChild(note);
    return wrap;
}

function renderDateTimeOnlyInput(field) {
    const inp = plainInput(field.type, field, 'value');
    inp.dataset.fieldKey = field.key;
    if (field.type !== 'time') return inp;
    const wrap = el('div');
    const note = el('div', 'form-text text-secondary small mt-1 uf-tz-note');
    note.textContent = LOCAL_TIME_NOTE;
    wrap.appendChild(inp);
    wrap.appendChild(note);
    return wrap;
}

// Read-only value text (+ zone for instants)
function readonlyText(field) {
    const v = field.value;
    if (v === null || v === undefined || v === '') return '–';
    if (isInstantField(field) && parseInstant(v)) return formatTyped('datetime', v, fieldZone(field));
    if (field.type === 'date' || field.type === 'time') return formatTyped(field.type, v);
    return v;
}

// ---------------------------------------------------------------------------
// App-defined lists – `type: user` fields
//
// The page supplies the users via UniForms.setUserProvider(source => Promise<[{username, role}]>).
// Without a provider (e.g. Designer preview), or when it fails, the field degrades to a
// plain text input so a record can still be edited.
// ---------------------------------------------------------------------------

let userProvider = null;

function textInput(field, placeholder) {
    const inp = el('input', 'form-control form-control-sm');
    inp.type = 'text';
    inp.placeholder = placeholder || '';
    inp.dataset.fieldKey = field.key;
    inp.value = field.value || '';
    inp.addEventListener('change', () => { field.value = inp.value || null; });
    return inp;
}

function renderUserInput(field) {
    const source = field.source || 'collection_members';
    if (!userProvider) return textInput(field, field.placeholder || 'username');
    const wrap = el('div');
    const sel = el('select', 'form-select form-select-sm');
    sel.dataset.fieldKey = field.key;
    sel.disabled = true;
    const addOpt = (value, label) => {
        const o = document.createElement('option');
        o.value = value;
        o.textContent = label;
        if ((field.value || '') === value) o.selected = true;
        sel.appendChild(o);
    };
    addOpt('', '– select user –');
    if (field.value) addOpt(field.value, field.value);   // until the list arrives
    sel.addEventListener('change', () => { field.value = sel.value || null; });
    wrap.appendChild(sel);
    Promise.resolve()
        .then(() => userProvider(source))
        .then(users => {
            if (!Array.isArray(users)) throw new Error('no user list');
            while (sel.firstChild) sel.removeChild(sel.firstChild);
            addOpt('', '– select user –');
            const names = users.map(u => u.username);
            users.forEach(u => addOpt(u.username, u.username));
            // keep a value that is not (or no longer) a member – e.g. older free-text records
            if (field.value && !names.includes(field.value)) addOpt(field.value, `${field.value} (not a user of this collection)`);
            sel.disabled = false;
        })
        .catch(() => { wrap.replaceChild(textInput(field, 'username'), sel); });
    return wrap;
}

// ---------------------------------------------------------------------------
// Field input widget factory
// ---------------------------------------------------------------------------

function renderFieldInput(field) {
    if (!field.editable) {
        const span = el('span', 'text-secondary fst-italic');
        span.textContent = readonlyText(field);
        const d = isInstantField(field) ? parseInstant(field.value) : null;
        if (!d) return span;
        span.title = `stored ${field.value}`;
        const wrap = el('div');
        const note = el('div', 'form-text text-secondary small uf-tz-note');
        note.textContent = `Time zone: ${zoneLabel(fieldZone(field), d)}`;
        wrap.appendChild(span);
        wrap.appendChild(note);
        return wrap;
    }

    // placeholder: UI hint only; example: pre-filled default value (both usable)
    const placeholder = field.placeholder || '';

    switch (field.type) {
        case 'textarea': {
            const ta = el('textarea', 'form-control form-control-sm bg-light');
            ta.rows = 3;
            ta.placeholder = placeholder;
            ta.value = field.value || '';
            ta.dataset.fieldKey = field.key;
            ta.addEventListener('change', () => { field.value = ta.value; });
            return ta;
        }
        case 'select': {
            const sel = el('select', 'form-select form-select-sm');
            sel.dataset.fieldKey = field.key;
            const emptyOpt = document.createElement('option');
            emptyOpt.value = '';
            emptyOpt.textContent = '– select –';
            sel.appendChild(emptyOpt);
            buildOptions(sel, field.options || [], field.value);
            sel.addEventListener('change', () => { field.value = sel.value || null; });

            if (field.option_hints) {
                const hint = el('div', 'form-text text-secondary small mt-1');
                const updateHint = () => {
                    hint.textContent = sel.value && field.option_hints[sel.value]
                        ? field.option_hints[sel.value] : '';
                };
                sel.addEventListener('change', updateHint);
                updateHint();
                const wrap = el('div');
                wrap.appendChild(sel);
                wrap.appendChild(hint);
                return wrap;
            }
            return sel;
        }
        case 'number': {
            const inp = el('input', 'form-control form-control-sm');
            inp.type = 'number';
            inp.placeholder = placeholder;
            inp.dataset.fieldKey = field.key;
            if (field.value != null) inp.value = field.value;
            inp.addEventListener('change', () => { field.value = inp.value !== '' ? Number(inp.value) : null; });
            return inp;
        }
        case 'user':
            return renderUserInput(field);
        case 'datetime':
            return renderDatetimeInput(field);
        case 'date':
        case 'time':
            return renderDateTimeOnlyInput(field);
        default: {
            const inp = el('input', 'form-control form-control-sm');
            inp.type = 'text';
            inp.placeholder = placeholder;
            inp.dataset.fieldKey = field.key;
            inp.value = field.value || '';
            inp.addEventListener('change', () => { field.value = inp.value || null; });
            return inp;
        }
    }
}

// ---------------------------------------------------------------------------
// Section renderers – core types
// ---------------------------------------------------------------------------

function renderForm(fields) {
    const wrap = el('div');
    fields.forEach(field => wrap.appendChild(renderFieldRow(field)));
    return wrap;
}

function renderFormSection(section) {
    const wrap = el('div');
    if (section.hint) {
        const hintEl = el('div', 'alert alert-info py-2 small mb-3');
        setHTML(hintEl, `<i class="bi bi-info-circle me-1"></i>${section.hint}`);
        wrap.appendChild(hintEl);
    }
    wrap.appendChild(renderForm(section.fields || []));
    applyConditionals(section.fields || [], wrap);
    return wrap;
}

// Header section – editable fields prominent, read-only auto fields as info grid
function renderHeader(section) {
    const wrap = el('div');
    const editableFields = (section.fields || []).filter(f => f.editable);
    const readonlyFields = (section.fields || []).filter(f => !f.editable);

    editableFields.forEach(field => {
        wrap.appendChild(renderFieldRow(field, 'form-label fw-semibold small mb-0', 'mb-3'));
    });

    if (readonlyFields.length > 0) {
        wrap.appendChild(renderInfoGrid(readonlyFields, 'col-md-4 col-lg-3', 'row g-2 mt-1 pt-2 border-top'));
    }

    applyConditionals(section.fields || [], wrap);
    return wrap;
}

// ---------------------------------------------------------------------------
// Table renderers
// ---------------------------------------------------------------------------

/**
 * Normalize columns to v2 format: [{key, label, type, editable, options}]
 *
 * Handles both v2 (columns is array of objects) and v1 (columns is array of
 * strings with separate column_labels / editable_columns / status_options).
 */
function normalizeColumns(section) {
    const cols = section.columns || [];
    if (!cols.length) return [];

    // v2: already in dict format
    if (typeof cols[0] === 'object') return cols;

    // v1: expand from string keys + separate properties
    const statusCol = section.status_column || 'status';
    return cols.map(key => ({
        key,
        label: section.column_labels?.[key] || key,
        editable: (section.editable_columns || []).includes(key),
        type: (section.column_options?.[key] || (key === statusCol && section.status_options))
            ? 'select' : 'text',
        options: section.column_options?.[key]
            || (key === statusCol ? section.status_options : null),
    }));
}

/**
 * Unified table renderer (v2 type: table).
 *
 * Each column can be:
 *   - read-only (editable: false, default) – displays text
 *   - editable text (editable: true, type: text) – text input
 *   - editable select (editable: true, type: select, options: [...]) – select
 *
 * Analyst-added rows (via "Add row") are fully editable regardless of column config.
 */
function renderTable(section) {
    const cols = normalizeColumns(section);
    const hasActions = section.allow_delete_row || section.allow_append_row;

    const thead = document.createElement('thead');
    const headTr = document.createElement('tr');
    headTr.className = 'table-light';
    const colZone = col => (col.display_tz === 'utc' ? 'UTC' : APP_TZ);
    cols.forEach(col => {
        const th = el('th', 'text-muted small');
        th.textContent = col.label;
        const zone = col.type === 'datetime' ? zoneLabel(colZone(col)) : col.type === 'time' ? 'local time' : null;
        if (zone) {
            const z = el('span', 'fw-normal ms-1 uf-tz-note');
            z.textContent = `(${zone})`;
            z.title = col.type === 'time' ? LOCAL_TIME_NOTE : 'Stored in UTC, shown in this time zone';
            th.appendChild(z);
        }
        headTr.appendChild(th);
    });
    if (hasActions) headTr.appendChild(el('th', ''));
    thead.appendChild(headTr);

    const tbody = document.createElement('tbody');

    const renderRow = (row) => {
        const tr = document.createElement('tr');
        cols.forEach(col => {
            const td = el('td', 'align-middle');
            const isEditable = row.user_added || col.editable;

            if (isEditable && col.type === 'select') {
                const sel = el('select', 'form-select form-select-sm border-0 p-0');
                const empty = document.createElement('option');
                empty.value = ''; empty.textContent = '–';
                sel.appendChild(empty);
                buildOptions(sel, col.options || [], row[col.key]);
                sel.addEventListener('change', () => { row[col.key] = sel.value || null; });
                td.appendChild(sel);
            } else if (isEditable && col.type === 'datetime') {
                td.appendChild(datetimeInput(row, col.key, colZone(col), 'form-control form-control-sm border-0 bg-transparent'));
            } else if (isEditable && (col.type === 'date' || col.type === 'time')) {
                td.appendChild(plainInput(col.type, row, col.key, 'form-control form-control-sm border-0 bg-transparent'));
            } else if (isEditable) {
                const inp = el('input', 'form-control form-control-sm border-0 bg-transparent');
                inp.type = 'text';
                inp.value = row[col.key] || '';
                inp.addEventListener('change', () => { row[col.key] = inp.value || null; });
                td.appendChild(inp);
            } else {
                td.className = 'small align-middle text-muted';
                td.textContent = formatTyped(col.type, row[col.key], colZone(col));
            }
            tr.appendChild(td);
        });

        if (hasActions) {
            const delTd = el('td', 'align-middle text-center');
            if (section.allow_delete_row || row.user_added) {
                delTd.appendChild(makeDeleteBtn(() => {
                    section.rows.splice(section.rows.indexOf(row), 1);
                    tr.remove();
                }));
            }
            tr.appendChild(delTd);
        }
        return tr;
    };

    (section.rows || []).forEach(row => tbody.appendChild(renderRow(row)));

    const table = el('table', 'table table-sm table-bordered mb-0');
    table.appendChild(thead);
    table.appendChild(tbody);

    const wrap = el('div');

    // Optional single hint above the table (blue info box, same as form sections)
    if (section.hint) {
        wrap.appendChild(el('div', 'alert alert-info py-2 small mb-3',
            `<i class="bi bi-info-circle me-1"></i>${section.hint}`));
    }

    const tableWrap = el('div', 'table-responsive');
    tableWrap.appendChild(table);
    wrap.appendChild(tableWrap);

    // Optional hint lines below the table (gray text, e.g. for action tables with role notes)
    if (section.hints) {
        section.hints.forEach(hint => {
            wrap.appendChild(el('div', 'form-text text-secondary small mt-2',
                `<i class="bi bi-info-circle me-1"></i>${hint}`));
        });
    }

    if (section.allow_append_row) {
        const addLabel = section.add_row_label || 'Add row';
        const addBtn = el('button', 'btn btn-outline-secondary btn-sm mt-2',
            `<i class="bi bi-plus me-1"></i>${addLabel}`);
        addBtn.addEventListener('click', () => {
            const newRow = Object.assign({}, section.append_row_template || {}, { user_added: true });
            cols.forEach(col => { if (!(col.key in newRow)) newRow[col.key] = null; });
            if (!section.rows) section.rows = [];
            section.rows.push(newRow);
            tbody.appendChild(renderRow(newRow));
        });
        wrap.appendChild(addBtn);
    }

    return wrap;
}

// Section group – Bootstrap accordion container
function renderSectionGroup(section) {
    const wrap = el('div');
    const acc = el('div', 'accordion accordion-flush');
    acc.id = `acc-${section.id}`;

    (section.subsections || []).forEach((sub, idx) => {
        const item = el('div', 'accordion-item border mb-2');
        const headerId = `sh-${section.id}-${sub.id}`;
        const bodyId = `sb-${section.id}-${sub.id}`;
        const isFirst = idx === 0;

        if (sub.always_expanded) {
            setHTML(item, `
                <h2 class="accordion-header" id="${headerId}">
                    <button class="accordion-button pe-none bg-light" type="button" style="cursor:default;opacity:1">
                        ${sub.title}
                        ${sub.note ? `<small class="text-muted ms-3">${sub.note}</small>` : ''}
                    </button>
                </h2>
                <div id="${bodyId}" class="accordion-collapse collapse show">
                    <div class="accordion-body pt-2" id="body-${bodyId}"></div>
                </div>`);
        } else {
            setHTML(item, `
                <h2 class="accordion-header" id="${headerId}">
                    <button class="accordion-button ${isFirst ? '' : 'collapsed'}"
                            type="button" data-bs-toggle="collapse"
                            data-bs-target="#${bodyId}" aria-expanded="${isFirst}">
                        ${sub.title}
                        ${sub.note ? `<small class="text-muted ms-3">${sub.note}</small>` : ''}
                    </button>
                </h2>
                <div id="${bodyId}" class="accordion-collapse collapse ${isFirst ? 'show' : ''}">
                    <div class="accordion-body pt-2" id="body-${bodyId}"></div>
                </div>`);
        }

        acc.appendChild(item);

        requestAnimationFrame(() => {
            const bodyEl = document.getElementById(`body-${bodyId}`);
            if (!bodyEl) return;
            const renderFn = renderers[sub.type];
            if (renderFn) bodyEl.appendChild(renderFn(sub));
            else bodyEl.appendChild(renderForm(sub.fields || []));
        });
    });

    wrap.appendChild(acc);
    return wrap;
}

// Checklist – step groups with checkboxes and analyst notes
function renderChecklist(section) {
    const wrap = el('div');

    (section.step_groups || []).forEach(group => {
        const groupEl = el('div', 'mb-4');

        // Flat steps (no title) when group.title is null
        if (group.title) {
            const titleEl = el('div', 'd-flex align-items-center gap-2 mb-2');
            setHTML(titleEl, `<span class="fw-semibold">${group.title}</span>
                ${group.note ? `<small class="text-muted">(${group.note})</small>` : ''}`);
            groupEl.appendChild(titleEl);
        }

        (group.hints || []).forEach(hint => {
            groupEl.appendChild(el('div', 'alert alert-secondary py-1 px-2 small mb-2',
                '<i class="bi bi-info-circle me-1"></i>' + hint));
        });
        (group.classification_hints || []).forEach(hint => {
            groupEl.appendChild(el('div', 'hint-classification py-2 px-3 small mb-2 rounded',
                '<i class="bi bi-diagram-3 me-1"></i>' + hint));
        });

        const stepsEl = el('div', 'border border-secondary rounded');
        (group.steps || []).forEach((step, idx) => {
            const stepEl = el('div',
                `p-3 ${idx < group.steps.length - 1 ? 'border-bottom border-secondary' : ''}`);

            // hint is a single string or array
            const hintLines = step.hint
                ? (Array.isArray(step.hint) ? step.hint : [step.hint])
                : [];
            const hintHtml = hintLines.map(h =>
                `<div class="form-text text-secondary mt-1"><i class="bi bi-info-circle me-1"></i>${h}</div>`
            ).join('');

            setHTML(stepEl, `
                <div class="d-flex gap-3">
                    <div class="flex-shrink-0 mt-1">
                        <input type="checkbox" class="form-check-input step-check"
                               id="chk-${step.id}" ${step.done ? 'checked' : ''}>
                    </div>
                    <div class="flex-grow-1">
                        <label for="chk-${step.id}" class="small mb-1 d-block" style="cursor:pointer">
                            ${step.action}
                        </label>
                        ${hintHtml}
                        <textarea class="form-control form-control-sm bg-light mt-2"
                                  rows="2" placeholder="Analyst note…"
                                  data-step-id="${step.id}"></textarea>
                    </div>
                </div>`);

            const chk = stepEl.querySelector('.step-check');
            chk.addEventListener('change', () => { step.done = chk.checked; });

            const ta = stepEl.querySelector('textarea');
            ta.value = step.analyst_note || '';
            ta.addEventListener('change', () => { step.analyst_note = ta.value || null; });

            stepsEl.appendChild(stepEl);
        });
        groupEl.appendChild(stepsEl);
        wrap.appendChild(groupEl);
    });

    if (section.result) {
        const resEl = el('div', 'mt-4');
        resEl.appendChild(el('div', 'fw-semibold mb-2',
            `<i class="bi bi-flag me-2 text-danger"></i>${section.result.title}`));

        if (section.result.notifications) {
            const notifEl = el('div', 'alert alert-info small mb-3');
            const notifs = section.result.notifications;
            let html = '<strong>Notifications:</strong><ul class="mb-0 mt-1">';
            if (notifs.length > 0 && typeof notifs[0] === 'object') {
                notifs.forEach(group => {
                    html += `<li class="fw-semibold mt-1">${group.condition}</li><ul class="mb-0">`;
                    (group.actions || []).forEach(a => { html += `<li>${a}</li>`; });
                    html += '</ul>';
                });
            } else {
                notifs.forEach(n => { html += `<li>${n}</li>`; });
            }
            html += '</ul>';
            setHTML(notifEl, html);
            resEl.appendChild(notifEl);
        }

        resEl.appendChild(renderForm(section.result.fields || []));
        wrap.appendChild(resEl);
    }

    return wrap;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

return {
    render:           renderSections,
    registerRenderer: (type, fn) => { renderers[type] = fn; },
    setUserProvider:  fn => { userProvider = typeof fn === 'function' ? fn : null; },
    // Date & time helpers (UTC storage ↔ app timezone display)
    time: { timezone: APP_TZ, dateFormat: DATE_FMT, parseInstant, formatInstant, formatDate, formatTime, formatTyped, zoneLabel },
    // Expose helpers for use by extensions
    _helpers: {
        el, setHTML, buildTableHead, buildOptions, makeDeleteBtn,
        renderFieldInput, renderInfoGrid, renderFieldRow, renderForm,
        normalizeColumns, evalExpr, applyConditionals,
    },
};

})();
