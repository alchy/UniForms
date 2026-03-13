/**
 * SOC Extension – RACI table renderer (type: raci_table)
 *
 * Read-only responsibility matrix. Cells containing 'R' (Responsible)
 * are highlighted in bold red.
 *
 * Registered via UniForms.registerRenderer().
 */

UniForms.registerRenderer('raci_table', function renderRaciTable(section) {
    const { el, setHTML, buildTableHead } = UniForms._helpers;

    const wrap = el('div');

    if (section.legend) {
        wrap.appendChild(el('div', 'text-secondary small mb-2 raci-legend',
            `<i class="bi bi-info-circle me-1"></i>${section.legend}`));
    }

    const tableWrap = el('div', 'table-responsive');
    const table = el('table', 'table table-sm table-bordered mb-0 data-table');

    table.appendChild(buildTableHead(section.columns || [], section.column_labels));

    const tbody = document.createElement('tbody');
    (section.rows || []).forEach(row => {
        const tr = document.createElement('tr');
        (section.columns || []).forEach(col => {
            const td = el('td', 'small align-middle');
            const val = row[col] || '–';
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
});
