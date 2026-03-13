/**
 * Forms4SOC – dynamický renderer JSON dokumentu incidentu
 *
 * ARCHITEKTURA (pro čtenáře znalé Pythonu):
 *
 * Tento soubor plní roli "view vrstvy" pro detail incidentu.
 * Analogie: místo serverového Jinja2 šablonování probíhá renderování
 * kompletně v prohlížeči z JSON dat.
 *
 * Tok dat (přehled):
 *   1. Backend vrátí JSON incidentu přes REST API
 *   2. renderSections() projde seznam sekcí a pro každou zavolá
 *      příslušnou render* funkci podle section.type (obdoba dispatch slovníku)
 *   3. render* funkce sestaví DOM elementy a vrátí je (místo HTML stringu)
 *   4. Analytik edituje pole → každá změna se okamžitě zapíše zpět do
 *      JS objektu (field.value = inp.value) – objekt je "živý", vždy aktuální
 *   5. Při kliknutí Uložit se JS objekt serializuje do JSON a odešle na backend
 *
 * Klíčové pojmy pro Pythonisty:
 *   el(tag, css, html)      pomocná factory – obdoba html.div(class_=...) v Pythonu
 *   setHTML(el, html)       bezpečné přiřazení HTML (viz sekce Sanitizace níže)
 *   addEventListener(ev, fn) registrace callbacku na událost (obdoba signal/slot)
 *   field.value             atribut JS objektu; mutace zde = mutace v caseDocument
 *   section.rows            pole JS objektů; splice()/push() přímo mění zdrojová data
 *
 * Namespace:
 *   Vše je zabaleno v IIFE a vystaveno přes globální objekt Forms4SOC:
 *   Forms4SOC.render(sections, container)        – vyrenderuje formulář
 *   Forms4SOC.registerRenderer(type, fn)         – registruje vlastní typ sekce
 */

const Forms4SOC = (() => {

// ---------------------------------------------------------------------------
// Sanitizace HTML – ochrana proti XSS
//
// Problem: obsah šablon (tituly, labely, hinty) se vkládá do DOM přes innerHTML,
// což by umožnilo spustit škodlivý JS kód vložený do JSON šablony.
//
// Řešení: DOMParser parsuje HTML v izolovaném dokumentu (skripty se nespustí),
// nebezpečné elementy a atributy se odstraní, a teprve pak se výsledek vloží do DOM.
// ---------------------------------------------------------------------------

function sanitizeHTML(html) {
    // DOMParser vytvoří oddělený dokument – parse proběhne, ale nic se nespustí
    const doc = new DOMParser().parseFromString(String(html), 'text/html');
    // Odstraň elementy, které mohou spouštět kód nebo načítat externí obsah
    doc.querySelectorAll('script, iframe, object, embed, link, meta').forEach(e => e.remove());
    // Odstraň event handlery (onclick, onmouseover ...) a javascript: href
    doc.querySelectorAll('*').forEach(e => {
        [...e.attributes].forEach(a => {
            if (/^on/i.test(a.name)) e.removeAttribute(a.name);
            if (a.name === 'href' && /^javascript:/i.test(a.value)) e.removeAttribute(a.name);
        });
    });
    return doc.body.innerHTML;
}

// Wrapper pro všechna přímá innerHTML přiřazení – vždy přes sanitizeHTML
function setHTML(element, html) {
    element.innerHTML = sanitizeHTML(html);
}

// ---------------------------------------------------------------------------
// Hlavní dispatcher – vstupní bod renderování
//
// Analogie v Pythonu:
//   def render_sections(sections, container):
//       container.clear()
//       for section in sections:
//           container.append(render_section(section))
// ---------------------------------------------------------------------------

// Vymaže kontejner a naplní ho vyrenderovanými sekcemi
function renderSections(sections, container) {
    container.innerHTML = '';
    sections.forEach(section => {
        const el = renderSection(section);
        if (el) container.appendChild(el);
    });
}

// renderFormSection je univerzální renderer pro type: form.
// Volitelný klíč section.hint zobrazí modrý informační box nad formulářem.
function renderFormSection(section) {
    const wrap = el('div');
    if (section.hint) {
        const hintEl = el('div', 'alert alert-info py-2 small mb-3');
        setHTML(hintEl, `<i class="bi bi-info-circle me-1"></i>${section.hint}`);
        wrap.appendChild(hintEl);
    }
    wrap.appendChild(renderForm(section.fields || []));
    return wrap;
}

// ---------------------------------------------------------------------------
// Registr rendererů – mapuje section.type na render funkci.
// Nový typ lze zaregistrovat zvenčí přes Forms4SOC.registerRenderer(type, fn)
// bez úpravy tohoto souboru.
// Analogie v Pythonu: dict dispatch { 'form': render_form, ... }
// ---------------------------------------------------------------------------

const renderers = {
    workbook_header:    renderWorkbookHeader,
    playbook_header:    renderWorkbookHeader,
    classification:     renderClassification,
    contact_table:      renderContactTable,
    section_group:      renderSectionGroup,
    form:               renderFormSection,
    assets_table:       renderAssetsTable,
    checklist:          renderChecklist,
    action_table:       renderActionTable,
    raci_table:         renderRaciTable,
};

// Obalí obsah sekce do karty (card) a zavolá příslušný renderer z registru.
// Neznámý typ → zobrazí surový JSON jako ladící výpis.
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
        // Neznámý typ sekce – zobraz surový JSON jako ladící výpis
        // textContent (ne innerHTML) zaručuje, že se JSON nevyinterpretuje jako HTML
        const pre = el('pre', 'text-secondary small mb-0');
        pre.textContent = JSON.stringify(section, null, 2);
        body.appendChild(pre);
    }

    wrapper.appendChild(body);
    return wrapper;
}

// ---------------------------------------------------------------------------
// Pomocné factory funkce
// ---------------------------------------------------------------------------

// Zkrácená factory pro DOM elementy – obdoba html.TAG(class_=cls, innerHTML=html)
// Třetí parametr html se sanitizuje před vložením (ochrana XSS)
function el(tag, cls, html) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html !== undefined) e.innerHTML = sanitizeHTML(html);
    return e;
}

// Sestaví thead tabulky ze seznamu sloupců a jejich popisků.
// extraCol=true přidá prázdný sloupec vpravo (pro tlačítka Smazat / přidat)
function buildTableHead(columns, columnLabels, extraCol = false) {
    const thead = document.createElement('thead');
    const tr = document.createElement('tr');
    columns.forEach(col => tr.appendChild(el('th', 'text-muted small', columnLabels?.[col] || col)));
    if (extraCol) tr.appendChild(el('th', 'text-muted small', ''));
    thead.appendChild(tr);
    return thead;
}

// Vytvoří tlačítko Smazat (odpadkový koš) a zaregistruje callback onClick
function makeDeleteBtn(onClick) {
    const btn = el('button', 'btn btn-link btn-sm text-danger p-0', '<i class="bi bi-trash"></i>');
    btn.addEventListener('click', onClick);
    return btn;
}

// Sestaví řádek: label vlevo (col-md-4) + input vpravo (col-md-8).
// Používá se v renderForm, renderWorkbookHeader, renderClassification.
function renderFieldRow(field, labelCls = 'form-label text-secondary small mb-0', rowMb = 'mb-2') {
    const row = el('div', `row ${rowMb} align-items-center`);
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

// Zobrazí read-only pole jako kompaktní info grid (label + hodnota pod sebou).
// Používá se v renderWorkbookHeader a renderClassification.
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

// Přidá options do existujícího <select> elementu a označí aktuálně vybranou hodnotu.
// Používá se v renderFieldInput (select), renderAssetsTable, renderActionTable.
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
// Widget factory pro jednotlivá formulářová pole
//
// Funkce přijme objekt field ze JSON šablony a vrátí odpovídající DOM vstupní prvek.
// Klíčová vlastnost: každý widget je "live-bound" na field.value –
// při změně inputu (onChange) se field.value okamžitě aktualizuje.
// Při serializaci (Uložit) se čte přímo z field.value, ne z DOM.
//
// Analogie v Pythonu: factory metoda vracející různé widgety (tkinter/Qt)
// podle parametru field.type.
// ---------------------------------------------------------------------------

function renderFieldInput(field) {
    // Read-only pole – zobrazí hodnotu jako text, bez vstupu
    if (!field.editable) {
        return el('span', 'text-secondary fst-italic',
            field.value !== null && field.value !== undefined ? field.value : '–');
    }

    switch (field.type) {
        case 'textarea': {
            const ta = el('textarea', 'form-control form-control-sm bg-light');
            ta.rows = 3;
            ta.placeholder = field.example || '';
            ta.value = field.value || '';
            ta.dataset.fieldKey = field.key;
            // Live binding: při každé změně obsahu zapsat zpět do JS objektu
            ta.addEventListener('change', () => { field.value = ta.value; });
            return ta;
        }
        case 'select': {
            const sel = el('select', 'form-select form-select-sm');
            sel.dataset.fieldKey = field.key;
            // Prázdná volba jako výchozí (null hodnota)
            const emptyOpt = document.createElement('option');
            emptyOpt.value = '';
            emptyOpt.textContent = '– vyberte –';
            sel.appendChild(emptyOpt);
            buildOptions(sel, field.options || [], field.value);
            sel.addEventListener('change', () => { field.value = sel.value || null; });

            // Volitelná nápověda pod selectem: zobrazí hint pro aktuálně vybranou možnost
            if (field.option_hints) {
                const hint = el('div', 'form-text text-secondary small mt-1');
                const updateHint = () => {
                    hint.textContent = sel.value && field.option_hints[sel.value]
                        ? field.option_hints[sel.value] : '';
                };
                sel.addEventListener('change', updateHint);
                updateHint(); // inicializuj hint pro předvyplněnou hodnotu
                const wrap = el('div');
                wrap.appendChild(sel);
                wrap.appendChild(hint);
                return wrap;
            }
            return sel;
        }
        case 'datetime': {
            const inp = el('input', 'form-control form-control-sm');
            inp.type = 'datetime-local';
            inp.dataset.fieldKey = field.key;
            // ISO timestamp zkrátíme na 16 znaků (YYYY-MM-DDTHH:MM) pro datetime-local input
            if (field.value) inp.value = field.value.substring(0, 16);
            inp.addEventListener('change', () => { field.value = inp.value || null; });
            return inp;
        }
        default: { // type 'text' a vše ostatní
            const inp = el('input', 'form-control form-control-sm');
            inp.type = 'text';
            inp.placeholder = field.example || '';
            inp.dataset.fieldKey = field.key;
            inp.value = field.value || '';
            inp.addEventListener('change', () => { field.value = inp.value || null; });
            return inp;
        }
    }
}

// ---------------------------------------------------------------------------
// Formulář (type: form)
//
// Renderuje seznam polí jako dvousloupcový grid: label vlevo, input vpravo.
// Volitelný klíč section.hint zobrazí modrý informační box nad formulářem.
// Používá renderFieldInput() pro každé pole.
// ---------------------------------------------------------------------------

function renderForm(fields) {
    const wrap = el('div');
    fields.forEach(field => {
        wrap.appendChild(renderFieldRow(field));
    });
    return wrap;
}

// ---------------------------------------------------------------------------
// Hlavička workbooku (type: workbook_header)
//
// Rozdíl od renderForm:
//   - Editovatelná pole jsou zobrazena prominentně nahoře (tučnější label)
//   - Read-only pole (case_id, verze, autor ...) jsou zobrazena jako kompaktní
//     informační mřížka pod čarou (nikoli jako formulářové řádky)
// ---------------------------------------------------------------------------

function renderWorkbookHeader(section) {
    const wrap = el('div');

    const editableFields = (section.fields || []).filter(f => f.editable);
    const readonlyFields = (section.fields || []).filter(f => !f.editable);

    editableFields.forEach(field => {
        wrap.appendChild(renderFieldRow(field, 'form-label fw-semibold small mb-0', 'mb-3'));
    });

    // Read-only metadata (case_id, verze ...) jako kompaktní info grid pod čarou
    if (readonlyFields.length > 0) {
        wrap.appendChild(renderInfoGrid(readonlyFields, 'col-md-4 col-lg-3', 'row g-2 mt-1 pt-2 border-top'));
    }

    return wrap;
}

// ---------------------------------------------------------------------------
// Klasifikace (type: classification)
//
// Panel s MITRE ATT&CK informacemi:
//   - Tactic a Technique jsou read-only (dané šablonou) → info grid
//   - Sub-technique je editovatelný select → analytik vyplní po Posouzení
//   - Data sources jsou zobrazeny jako badge seznam
// ---------------------------------------------------------------------------

function renderClassification(section) {
    const wrap = el('div');

    // data_sources má vlastní rendering (badge seznam), zpracuj ho zvlášť
    const mainFields = (section.fields || []).filter(f => f.key !== 'data_sources');
    const readonlyFields = mainFields.filter(f => !f.editable);
    const editableFields = mainFields.filter(f => f.editable);

    // Read-only MITRE pole jako kompaktní info grid
    if (readonlyFields.length > 0) {
        wrap.appendChild(renderInfoGrid(readonlyFields, 'col-md-6 col-lg-4', 'row g-2 mb-2'));
    }

    // Editovatelná pole (sub-technique select) jako standardní form řádky
    if (editableFields.length > 0) {
        const editRow = el('div', 'mt-2 pt-2 border-top');
        editableFields.forEach(field => editRow.appendChild(renderFieldRow(field)));
        wrap.appendChild(editRow);
    }

    // Data sources jako badge seznam (pole s klíčem 'data_sources')
    const dsField = (section.fields || []).find(f => f.key === 'data_sources');
    if (dsField && dsField.value) {
        // Hodnota může být pole nebo CSV string – normalizuj na pole
        const sources = Array.isArray(dsField.value)
            ? dsField.value
            : String(dsField.value).split(',').map(s => s.trim()).filter(Boolean);
        const dsWrap = el('div', 'mt-2');
        dsWrap.appendChild(el('span', 'text-muted small me-2', dsField.label + ':'));
        sources.forEach(src => {
            dsWrap.appendChild(el('span', 'badge bg-secondary-subtle text-secondary border border-secondary-subtle me-1', src));
        });
        wrap.appendChild(dsWrap);
    }

    return wrap;
}

// ---------------------------------------------------------------------------
// Kontaktní tabulka (type: contact_table)
//
// Tabulka kontaktů pro investigaci a eskalaci.
// Sloupce v editable_columns jsou editovatelné inline (input bez ohraničení).
// Analytik může přidávat vlastní řádky (allow_append); ty jsou plně editovatelné
// a mají navíc tlačítko Smazat.
// Řádky ze šablony (předdefinované kontakty) nejsou smazatelné.
// ---------------------------------------------------------------------------

function renderContactTable(section) {
    const wrap = el('div');
    const tableWrap = el('div', 'table-responsive');
    const table = el('table', 'table table-sm table-bordered mb-0');

    // Prázdný extra sloupec vpravo pro tlačítka Smazat (jen když lze přidávat řádky)
    table.appendChild(buildTableHead(section.columns || [], section.column_labels, section.allow_append));

    const tbody = document.createElement('tbody');

    // Vnitřní funkce pro render jednoho řádku – zavolá se pro každý existující
    // i nově přidaný řádek (closure přes section a tbody)
    const renderContactRow = (row) => {
        const tr = document.createElement('tr');
        (section.columns || []).forEach(col => {
            const td = document.createElement('td');
            // Analytik přidané řádky jsou plně editovatelné; u šablonových jen editable_columns
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

        // Sloupec pro tlačítko Smazat – jen pro analytiky přidané řádky
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
            '<i class="bi bi-plus me-1"></i>Přidat řádek');
        addBtn.addEventListener('click', () => {
            // Nový řádek zkopíruje strukturu append_row_template ze šablony
            const newRow = Object.assign({}, section.append_row_template || {}, {analyst_added: true});
            if (!section.rows) section.rows = [];
            section.rows.push(newRow);
            tbody.appendChild(renderContactRow(newRow));
        });
        wrap.appendChild(addBtn);
    }

    return wrap;
}

// ---------------------------------------------------------------------------
// Section group – accordion kontejner (type: section_group)
//
// Sdružuje více podsekce do Bootstrap accordionu. Každá podsekce je
// samostatný accordion item s vlastním nadpisem a obsahem.
//
// Pozn. k requestAnimationFrame:
//   Obsah podsekce se renderuje až po připojení accordion struktury do DOMu.
//   requestAnimationFrame počká na nejbližší překreslení prohlížeče, čímž
//   zaručí, že getElementById() prvek najde. Analogie: asyncio.create_task()
//   – odloží vykonání na příští iteraci event loop.
// ---------------------------------------------------------------------------

function renderSectionGroup(section) {
    const wrap = el('div');
    const acc = el('div', 'accordion accordion-flush');
    acc.id = `acc-${section.id}`;

    (section.subsections || []).forEach((sub, idx) => {
        const item = el('div', 'accordion-item border mb-2');
        const headerId = `sh-${section.id}-${sub.id}`;
        const bodyId = `sb-${section.id}-${sub.id}`;
        const isFirst = idx === 0;

        // always_expanded: podsekce bez možnosti sbalení (statický nadpis, vždy otevřeno)
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
            // Standardní accordion – první podsekce je výchozně otevřena
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

        // Render obsahu podsekce odložíme na příští frame – element musí být v DOMu
        // aby ho getElementById() našel (setHTML výše ho teprve vytváří)
        requestAnimationFrame(() => {
            const bodyEl = document.getElementById(`body-${bodyId}`);
            if (!bodyEl) return;
            switch (sub.type) {
                case 'form':         bodyEl.appendChild(renderForm(sub.fields || [])); break;
                case 'assets_table': bodyEl.appendChild(renderAssetsTable(sub)); break;
                default:             bodyEl.appendChild(renderForm(sub.fields || []));
            }
        });
    });

    wrap.appendChild(acc);
    return wrap;
}

// ---------------------------------------------------------------------------
// Tabulka dotčených aktiv (type: assets_table)
//
// Všechny buňky jsou editovatelné. Sloupce v column_options se renderují
// jako <select> (dropdown), ostatní jako textový input.
// Analytik může přidávat i mazat libovolné řádky.
// ---------------------------------------------------------------------------

function renderAssetsTable(section) {
    const wrap = el('div');

    // Volitelný hint – zobrazí se jako oranžové varování nad tabulkou
    if (section.hint) {
        wrap.appendChild(el('div', 'alert alert-warning alert-sm py-2 small mb-3',
            `<i class="bi bi-exclamation-triangle me-1"></i>${section.hint}`));
    }

    const tableWrap = el('div', 'table-responsive');
    const table = el('table', 'table table-sm table-bordered mb-2');

    // Extra sloupec vpravo vždy (pro tlačítka Smazat)
    table.appendChild(buildTableHead(section.columns || [], section.column_labels, true));

    const tbody = document.createElement('tbody');
    tbody.id = `assets-body-${section.id}`;

    const renderAssetRow = (row) => {
        const tr = document.createElement('tr');
        (section.columns || []).forEach(col => {
            const td = document.createElement('td');
            const opts = section.column_options?.[col];
            if (opts) {
                // Sloupec s předdefinovanými hodnotami → <select>
                const sel = el('select', 'form-select form-select-sm border-0');
                buildOptions(sel, opts, row[col]);
                sel.addEventListener('change', () => { row[col] = sel.value; });
                td.appendChild(sel);
            } else {
                // Ostatní sloupce → volný textový vstup
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

    (section.rows || []).forEach(row => tbody.appendChild(renderAssetRow(row)));
    table.appendChild(tbody);
    tableWrap.appendChild(table);
    wrap.appendChild(tableWrap);

    const addBtn = el('button', 'btn btn-outline-secondary btn-sm',
        '<i class="bi bi-plus me-1"></i>Přidat asset');
    addBtn.addEventListener('click', () => {
        const newRow = {};
        (section.columns || []).forEach(col => { newRow[col] = null; });
        if (!section.rows) section.rows = [];
        section.rows.push(newRow);
        tbody.appendChild(renderAssetRow(newRow));
    });
    wrap.appendChild(addBtn);
    return wrap;
}

// ---------------------------------------------------------------------------
// Checklist (type: checklist)
//
// Kontrolní seznam kroků organizovaných do skupin (step_groups).
// Každá skupina může obsahovat:
//   - hints: operační nápovědy (šedé)
//   - classification_hints: klasifikační vodítka True/False Positive (žluté)
//   - steps: jednotlivé kroky s checkboxem a textovým polem pro poznámku
//
// Live binding pro kroky:
//   - step.done       ← checkbox.checked
//   - step.analyst_note ← textarea.value
// ---------------------------------------------------------------------------

function renderChecklist(section) {
    const wrap = el('div');

    (section.step_groups || []).forEach(group => {
        const groupEl = el('div', 'mb-4');

        const titleEl = el('div', 'd-flex align-items-center gap-2 mb-2');
        setHTML(titleEl, `<span class="fw-semibold">${group.title}</span>
            ${group.note ? `<small class="text-muted">(${group.note})</small>` : ''}`);
        groupEl.appendChild(titleEl);

        // Operační nápovědy (šedé informační boxy)
        (group.hints || []).forEach(hint => {
            groupEl.appendChild(el('div', 'alert alert-secondary py-1 px-2 small mb-2',
                '<i class="bi bi-info-circle me-1"></i>' + hint));
        });
        // Klasifikační vodítka (žluté boxy s ikonou)
        (group.classification_hints || []).forEach(hint => {
            groupEl.appendChild(el('div', 'hint-classification py-2 px-3 small mb-2 rounded',
                '<i class="bi bi-diagram-3 me-1"></i>' + hint));
        });

        const stepsEl = el('div', 'border border-secondary rounded');
        (group.steps || []).forEach((step, idx) => {
            const stepEl = el('div',
                `p-3 ${idx < group.steps.length - 1 ? 'border-bottom border-secondary' : ''}`);

            // Struktura kroku: checkbox vlevo + label s textem akce + textarea pro poznámku
            // Textarea hodnotu nastavujeme přes .value (ne přes innerHTML) aby se předešlo
            // problémům s escapováním speciálních znaků v poznámce analytika
            setHTML(stepEl, `
                <div class="d-flex gap-3">
                    <div class="flex-shrink-0 mt-1">
                        <input type="checkbox" class="form-check-input step-check"
                               id="chk-${step.id}" ${step.done ? 'checked' : ''}>
                    </div>
                    <div class="flex-grow-1">
                        <label for="chk-${step.id}" class="small mb-2 d-block" style="cursor:pointer">
                            ${step.action}
                        </label>
                        <textarea class="form-control form-control-sm bg-light"
                                  rows="2" placeholder="${step.example || 'Poznámka analytika...'}"
                                  data-step-id="${step.id}"></textarea>
                    </div>
                </div>`);

            const chk = stepEl.querySelector('.step-check');
            chk.addEventListener('change', () => { step.done = chk.checked; });

            const ta = stepEl.querySelector('textarea');
            ta.value = step.analyst_note || ''; // hodnota přes .value, ne přes innerHTML
            ta.addEventListener('change', () => { step.analyst_note = ta.value || null; });

            stepsEl.appendChild(stepEl);
        });
        groupEl.appendChild(stepsEl);
        wrap.appendChild(groupEl);
    });

    // Volitelný výsledkový blok na konci checklistu (result.fields + result.notifications)
    if (section.result) {
        const resEl = el('div', 'mt-4');
        resEl.appendChild(el('div', 'fw-semibold mb-2',
            `<i class="bi bi-flag me-2 text-danger"></i>${section.result.title}`));

        if (section.result.notifications) {
            const notifEl = el('div', 'alert alert-info small mb-3');
            const notifs = section.result.notifications;
            // Notifikace mohou být buď pole stringů, nebo pole objektů {condition, actions}
            let html = '<strong>Notifikace:</strong><ul class="mb-0 mt-1">';
            if (notifs.length > 0 && typeof notifs[0] === 'object') {
                notifs.forEach(group => {
                    html += `<li class="fw-semibold mt-1">${group.condition}</li>`;
                    html += '<ul class="mb-0">';
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
// Tabulka akcí Odezva (type: action_table)
//
// Tabulka s předdefinovanými akcemi. Analytik edituje stav každé akce
// (sloupec status) z dropdown seznamu status_options.
// Analytik může přidávat vlastní akce (allow_append) a mazat řádky (allow_delete).
// Komunikační tabulky (dříve notification_table) se také renderují tímto rendererem.
// ---------------------------------------------------------------------------

function renderActionTable(section) {
    const wrap = el('div');
    const tableWrap = el('div', 'table-responsive');
    const table = el('table', 'table table-sm table-bordered mb-0');

    const hasActions = section.allow_delete || section.allow_append;
    table.appendChild(buildTableHead(section.columns || [], section.column_labels, hasActions));

    const tbody = document.createElement('tbody');

    const renderActionRow = (row) => {
        const tr = document.createElement('tr');
        (section.columns || []).forEach(col => {
            const td = el('td', 'small align-middle');
            const statusCol = section.status_column || 'status';
            const isStatus = col === statusCol && (section.editable_columns || []).includes(col) && section.status_options;

            if (isStatus) {
                // Sloupec Stav – dropdown z předdefinovaných možností
                const sel = el('select', 'form-select form-select-sm border-0');
                const emptyOpt = document.createElement('option');
                emptyOpt.value = ''; emptyOpt.textContent = '–';
                sel.appendChild(emptyOpt);
                buildOptions(sel, section.status_options, row[col]);
                sel.addEventListener('change', () => { row[col] = sel.value || null; });
                td.appendChild(sel);
            } else if (row.analyst_added) {
                // Analytik přidané řádky jsou plně editovatelné (všechny sloupce)
                const inp = el('input', 'form-control form-control-sm border-0 p-0');
                inp.type = 'text';
                inp.value = row[col] || '';
                inp.style.background = 'transparent';
                inp.addEventListener('change', () => { row[col] = inp.value || null; });
                td.appendChild(inp);
            } else {
                // Šablonové řádky – ostatní sloupce jsou read-only text
                td.textContent = row[col] || '–';
            }
            tr.appendChild(td);
        });

        if (hasActions) {
            const delTd = el('td', 'align-middle text-center');
            // Smazat lze: vždy pokud allow_delete=true, nebo analytikův vlastní řádek
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

    (section.rows || []).forEach(row => tbody.appendChild(renderActionRow(row)));
    table.appendChild(tbody);
    tableWrap.appendChild(table);
    wrap.appendChild(tableWrap);

    // Volitelné hints pod tabulkou (šedé informační texty)
    if (section.hints) {
        section.hints.forEach(hint => {
            wrap.appendChild(el('div', 'form-text text-secondary small mt-2',
                `<i class="bi bi-info-circle me-1"></i>${hint}`));
        });
    }

    if (section.allow_append) {
        const addBtn = el('button', 'btn btn-outline-secondary btn-sm mt-2',
            '<i class="bi bi-plus me-1"></i>Přidat akci');
        addBtn.addEventListener('click', () => {
            const newRow = Object.assign({}, section.append_row_template || {}, {analyst_added: true});
            if (!section.rows) section.rows = [];
            section.rows.push(newRow);
            tbody.appendChild(renderActionRow(newRow));
        });
        wrap.appendChild(addBtn);
    }

    return wrap;
}

// ---------------------------------------------------------------------------
// RACI tabulka (type: raci_table) – pouze pro čtení
//
// Buňky obsahující 'R' jsou zvýrazněny tučně červeně (Responsible).
// Tabulka je čistě informativní, analytik ji needituje.
// ---------------------------------------------------------------------------

function renderRaciTable(section) {
    const wrap = el('div');

    if (section.legend) {
        wrap.appendChild(el('div', 'text-secondary small mb-2',
            `<i class="bi bi-info-circle me-1"></i>${section.legend}`));
    }

    const tableWrap = el('div', 'table-responsive');
    const table = el('table', 'table table-sm table-bordered mb-0');

    table.appendChild(buildTableHead(section.columns || [], section.column_labels));

    const tbody = document.createElement('tbody');
    (section.rows || []).forEach(row => {
        const tr = document.createElement('tr');
        (section.columns || []).forEach(col => {
            const td = el('td', 'small align-middle');
            const val = row[col] || '–';
            // Buňky s 'R' (Responsible) zvýrazni tučně červeně
            if (val.includes('R')) setHTML(td, `<strong class="text-danger">${val}</strong>`);
            else td.textContent = val;
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    tableWrap.appendChild(table);
    wrap.appendChild(tableWrap);
    return wrap;
}

// ---------------------------------------------------------------------------
// Veřejné API – jediné symboly viditelné z okolního kódu
// ---------------------------------------------------------------------------

return {
    render:           renderSections,
    registerRenderer: (type, fn) => { renderers[type] = fn; },
};

})(); // konec Forms4SOC IIFE
