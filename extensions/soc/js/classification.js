/**
 * SOC Extension – Classification section renderer (type: classification)
 *
 * Renders a MITRE ATT&CK classification panel:
 *   - Tactic and Technique: read-only (from template meta) → info grid
 *   - Sub-technique: editable select → analyst fills in after assessment
 *   - Data sources: rendered as badge list
 *
 * Registered via UniForms.registerRenderer() so it extends the core without
 * modifying uniforms.js.
 */

UniForms.registerRenderer('classification', function renderClassification(section) {
    const { el, setHTML, renderInfoGrid, renderFieldRow, renderFieldInput } = UniForms._helpers;

    const wrap = el('div');

    const mainFields = (section.fields || []).filter(f => f.key !== 'data_sources');
    const readonlyFields = mainFields.filter(f => !f.editable);
    const editableFields = mainFields.filter(f => f.editable);

    if (readonlyFields.length > 0) {
        wrap.appendChild(renderInfoGrid(readonlyFields, 'col-md-6 col-lg-4', 'row g-2 mb-2'));
    }

    if (editableFields.length > 0) {
        const editRow = el('div', 'mt-2 pt-2 border-top');
        editableFields.forEach(field => editRow.appendChild(renderFieldRow(field)));
        wrap.appendChild(editRow);
    }

    const dsField = (section.fields || []).find(f => f.key === 'data_sources');
    if (dsField && dsField.value) {
        const sources = Array.isArray(dsField.value)
            ? dsField.value
            : String(dsField.value).split(',').map(s => s.trim()).filter(Boolean);
        const dsWrap = el('div', 'mt-2');
        dsWrap.appendChild(el('span', 'text-muted small me-2', (dsField.label || 'Data sources') + ':'));
        sources.forEach(src => {
            dsWrap.appendChild(el('span', 'badge bg-secondary-subtle text-secondary border border-secondary-subtle me-1', src));
        });
        wrap.appendChild(dsWrap);
    }

    return wrap;
});
