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
 * Section types provided by this core file:
 *   header, form, checklist, table,
 *   section_group, contact_table, item_table, task_table
 *   (workbook_header, playbook_header, record_header, action_table, assets_table
 *    are kept as aliases for existing templates)
 *
 * v2 template schema features supported:
 *   - type: header   (generic header, alias for workbook_header)
 *   - type: table    (unified table with per-column type/options/editable)
 *   - auto: <source> fields (resolved by backend; rendered read-only)
 *   - visible_if: "field == 'value'"  (conditional field visibility)
 *   - required_if: "field == 'value'" (conditional required indicator)
 *   - placeholder: "..."              (UI hint, not saved as value)
 *   - flat steps: (resolved by backend into step_groups with null title)
 *
 * Domain-specific section types (e.g. classification, raci_table for SOC)
 * are provided by extension JS files loaded after this file.
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
    // v2 generic types
    header:           renderHeader,
    table:            renderTable,
    // v1 type aliases (kept for existing templates)
    workbook_header:  renderHeader,
    playbook_header:  renderHeader,
    record_header:    renderHeader,
    contact_table:    renderContactTable,
    item_table:       renderItemTable,
    assets_table:     renderItemTable,
    task_table:       renderTaskTable,
    action_table:     renderTaskTable,
    // shared types
    section_group:    renderSectionGroup,
    form:             renderFormSection,
    fields:           renderFormSection,   // alias: type: fields → form
    checklist:        renderChecklist,
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
        const val = field.value !== null && field.value !== undefined ? field.value : '–';
        setHTML(col, `<div class="d-flex flex-column">
            <span class="text-muted small">${field.label}</span>
            <span class="small fw-semibold">${val}</span>
        </div>`);
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
// Field input widget factory
// ---------------------------------------------------------------------------

function renderFieldInput(field) {
    if (!field.editable) {
        return el('span', 'text-secondary fst-italic',
            field.value !== null && field.value !== undefined ? field.value : '–');
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
        case 'datetime': {
            const inp = el('input', 'form-control form-control-sm');
            inp.type = 'datetime-local';
            inp.dataset.fieldKey = field.key;
            if (field.value) inp.value = field.value.substring(0, 16);
            inp.addEventListener('change', () => { field.value = inp.value || null; });
            return inp;
        }
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
// Handles: type: header (v2), workbook_header / playbook_header / record_header (v1)
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
    const hasActions = section.allow_delete || section.allow_append;

    const thead = document.createElement('thead');
    const headTr = document.createElement('tr');
    headTr.className = 'table-light';
    cols.forEach(col => headTr.appendChild(el('th', 'text-muted small', col.label)));
    if (hasActions) headTr.appendChild(el('th', ''));
    thead.appendChild(headTr);

    const tbody = document.createElement('tbody');

    const renderRow = (row) => {
        const tr = document.createElement('tr');
        cols.forEach(col => {
            const td = el('td', 'align-middle');
            const isEditable = row.analyst_added || col.editable;

            if (isEditable && col.type === 'select') {
                const sel = el('select', 'form-select form-select-sm border-0 p-0');
                const empty = document.createElement('option');
                empty.value = ''; empty.textContent = '–';
                sel.appendChild(empty);
                buildOptions(sel, col.options || [], row[col.key]);
                sel.addEventListener('change', () => { row[col.key] = sel.value || null; });
                td.appendChild(sel);
            } else if (isEditable) {
                const inp = el('input', 'form-control form-control-sm border-0 bg-transparent');
                inp.type = 'text';
                inp.value = row[col.key] || '';
                inp.addEventListener('change', () => { row[col.key] = inp.value || null; });
                td.appendChild(inp);
            } else {
                td.className = 'small align-middle text-muted';
                td.textContent = row[col.key] || '–';
            }
            tr.appendChild(td);
        });

        if (hasActions) {
            const delTd = el('td', 'align-middle text-center');
            if (section.allow_delete || row.analyst_added) {
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
    const tableWrap = el('div', 'table-responsive');
    tableWrap.appendChild(table);
    wrap.appendChild(tableWrap);

    if (section.allow_append) {
        const addLabel = section.add_row_label || 'Add row';
        const addBtn = el('button', 'btn btn-outline-secondary btn-sm mt-2',
            `<i class="bi bi-plus me-1"></i>${addLabel}`);
        addBtn.addEventListener('click', () => {
            const newRow = { analyst_added: true };
            cols.forEach(col => { newRow[col.key] = null; });
            if (!section.rows) section.rows = [];
            section.rows.push(newRow);
            tbody.appendChild(renderRow(newRow));
        });
        wrap.appendChild(addBtn);
    }

    return wrap;
}

// Contact table – predefined rows with selectively editable columns (v1)
function renderContactTable(section) {
    const wrap = el('div');
    const tableWrap = el('div', 'table-responsive');
    const table = el('table', 'table table-sm table-bordered mb-0');

    table.appendChild(buildTableHead(section.columns || [], section.column_labels, section.allow_append));

    const tbody = document.createElement('tbody');

    const renderContactRow = (row) => {
        const tr = document.createElement('tr');
        (section.columns || []).forEach(col => {
            const td = document.createElement('td');
            const editable = row.analyst_added || (section.editable_columns || []).includes(col);
            if (editable) {
                const inp = el('input', 'form-control form-control-sm border-0 p-0');
                inp.type = 'text';
                inp.value = row[col] || '';
                inp.placeholder = row[col + '_example'] || '';
                inp.style.background = 'transparent';
                inp.addEventListener('change', () => { row[col] = inp.value || null; });
                td.appendChild(inp);
            } else {
                td.className = 'small align-middle';
                td.textContent = row[col] || '–';
            }
            tr.appendChild(td);
        });

        if (section.allow_append) {
            const delTd = document.createElement('td');
            if (row.analyst_added) {
                delTd.appendChild(makeDeleteBtn(() => {
                    section.rows.splice(section.rows.indexOf(row), 1);
                    tr.remove();
                }));
            }
            tr.appendChild(delTd);
        }
        return tr;
    };

    (section.rows || []).forEach(row => tbody.appendChild(renderContactRow(row)));
    table.appendChild(tbody);
    tableWrap.appendChild(table);
    wrap.appendChild(tableWrap);

    if (section.allow_append) {
        const addBtn = el('button', 'btn btn-outline-secondary btn-sm mt-2',
            '<i class="bi bi-plus me-1"></i>Add row');
        addBtn.addEventListener('click', () => {
            const newRow = Object.assign({}, section.append_row_template || {}, { analyst_added: true });
            if (!section.rows) section.rows = [];
            section.rows.push(newRow);
            tbody.appendChild(renderContactRow(newRow));
        });
        wrap.appendChild(addBtn);
    }

    return wrap;
}

// Item table – fully editable table with add/delete rows (v1 generic assets_table)
function renderItemTable(section) {
    const wrap = el('div');

    if (section.hint) {
        wrap.appendChild(el('div', 'alert alert-warning alert-sm py-2 small mb-3',
            `<i class="bi bi-exclamation-triangle me-1"></i>${section.hint}`));
    }

    const tableWrap = el('div', 'table-responsive');
    const table = el('table', 'table table-sm table-bordered mb-2');
    table.appendChild(buildTableHead(section.columns || [], section.column_labels, true));

    const tbody = document.createElement('tbody');
    tbody.id = `items-body-${section.id}`;

    const renderItemRow = (row) => {
        const tr = document.createElement('tr');
        (section.columns || []).forEach(col => {
            const td = document.createElement('td');
            const opts = section.column_options?.[col];
            if (opts) {
                const sel = el('select', 'form-select form-select-sm border-0');
                buildOptions(sel, opts, row[col]);
                sel.addEventListener('change', () => { row[col] = sel.value; });
                td.appendChild(sel);
            } else {
                const inp = el('input', 'form-control form-control-sm border-0');
                inp.type = 'text';
                inp.value = row[col] || '';
                inp.addEventListener('change', () => { row[col] = inp.value || null; });
                td.appendChild(inp);
            }
            tr.appendChild(td);
        });

        const delTd = document.createElement('td');
        delTd.appendChild(makeDeleteBtn(() => {
            section.rows.splice(section.rows.indexOf(row), 1);
            tr.remove();
        }));
        tr.appendChild(delTd);
        return tr;
    };

    (section.rows || []).forEach(row => tbody.appendChild(renderItemRow(row)));
    table.appendChild(tbody);
    tableWrap.appendChild(table);
    wrap.appendChild(tableWrap);

    const addLabel = section.add_row_label || 'Add row';
    const addBtn = el('button', 'btn btn-outline-secondary btn-sm',
        `<i class="bi bi-plus me-1"></i>${addLabel}`);
    addBtn.addEventListener('click', () => {
        const newRow = {};
        (section.columns || []).forEach(col => { newRow[col] = null; });
        if (!section.rows) section.rows = [];
        section.rows.push(newRow);
        tbody.appendChild(renderItemRow(newRow));
    });
    wrap.appendChild(addBtn);
    return wrap;
}

// Task table – table with status column (v1 action_table)
function renderTaskTable(section) {
    const wrap = el('div');
    const tableWrap = el('div', 'table-responsive');
    const table = el('table', 'table table-sm table-bordered mb-0');

    const hasActions = section.allow_delete || section.allow_append;
    table.appendChild(buildTableHead(section.columns || [], section.column_labels, hasActions));

    const tbody = document.createElement('tbody');

    const renderTaskRow = (row) => {
        const tr = document.createElement('tr');
        (section.columns || []).forEach(col => {
            const td = el('td', 'small align-middle');
            const statusCol = section.status_column || 'status';
            const isStatus = col === statusCol && (section.editable_columns || []).includes(col) && section.status_options;

            if (isStatus) {
                const sel = el('select', 'form-select form-select-sm border-0');
                const emptyOpt = document.createElement('option');
                emptyOpt.value = ''; emptyOpt.textContent = '–';
                sel.appendChild(emptyOpt);
                buildOptions(sel, section.status_options, row[col]);
                sel.addEventListener('change', () => { row[col] = sel.value || null; });
                td.appendChild(sel);
            } else if (row.analyst_added) {
                const inp = el('input', 'form-control form-control-sm border-0 p-0');
                inp.type = 'text';
                inp.value = row[col] || '';
                inp.style.background = 'transparent';
                inp.addEventListener('change', () => { row[col] = inp.value || null; });
                td.appendChild(inp);
            } else {
                td.textContent = row[col] || '–';
            }
            tr.appendChild(td);
        });

        if (hasActions) {
            const delTd = el('td', 'align-middle text-center');
            if (section.allow_delete || row.analyst_added) {
                delTd.appendChild(makeDeleteBtn(() => {
                    section.rows.splice(section.rows.indexOf(row), 1);
                    tr.remove();
                }));
            }
            tr.appendChild(delTd);
        }
        return tr;
    };

    (section.rows || []).forEach(row => tbody.appendChild(renderTaskRow(row)));
    table.appendChild(tbody);
    tableWrap.appendChild(table);
    wrap.appendChild(tableWrap);

    if (section.hints) {
        section.hints.forEach(hint => {
            wrap.appendChild(el('div', 'form-text text-secondary small mt-2',
                `<i class="bi bi-info-circle me-1"></i>${hint}`));
        });
    }

    if (section.allow_append) {
        const addLabel = section.add_row_label || 'Add row';
        const addBtn = el('button', 'btn btn-outline-secondary btn-sm mt-2',
            `<i class="bi bi-plus me-1"></i>${addLabel}`);
        addBtn.addEventListener('click', () => {
            const newRow = Object.assign({}, section.append_row_template || {}, { analyst_added: true });
            if (!section.rows) section.rows = [];
            section.rows.push(newRow);
            tbody.appendChild(renderTaskRow(newRow));
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
    // Expose helpers for use by extensions
    _helpers: {
        el, setHTML, buildTableHead, buildOptions, makeDeleteBtn,
        renderFieldInput, renderInfoGrid, renderFieldRow, renderForm,
        normalizeColumns, evalExpr, applyConditionals,
    },
};

})();
