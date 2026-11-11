#!/usr/bin/env node
/**
 * Unit test of the Collection Designer model operations (no browser needed).
 *
 *   node scripts/test_designer_model.js
 *
 * Covers the pure functions in uniforms/static/js/designer_model.js: adding,
 * moving, duplicating and deleting nodes, shorthand-preserving edits
 * (auto / auto_value, string steps, flat checklists) and placement rules.
 */
const assert = require('node:assert/strict');
const path = require('node:path');
const M = require(path.join(__dirname, '..', 'uniforms', 'static', 'js', 'designer_model.js'));

let passed = 0;
function test(name, fn) { fn(); passed++; console.log('ok  ', name); }

const tpl = () => ({
    template_id: 't-v1', name: 'T', version: '1.0',
    sections: [
        {id: 'header', title: 'H', type: 'header', fields: [
            {key: 'record_id', label: 'ID', auto: 'record_id'},
            {key: 'owner', label: 'Owner', auto_value: 'current_user', editable: false},
            {key: 'title', label: 'Title', custom_key: {a: 1}},
        ]},
        {id: 'form1', title: 'F', type: 'form', fields: [{key: 'a', label: 'A'}]},
        {id: 'chk', title: 'C', type: 'checklist', steps: ['one', {action: 'two', hint: 'h'}]},
        {id: 'tab', title: 'T', type: 'table', columns: [{key: 'c1', label: 'C1'}]},
        {id: 'grp', title: 'G', type: 'section_group', subsections: [
            {id: 'sub1', title: 'S1', type: 'form', fields: []},
        ]},
    ],
});

test('kindOf / sectionPathOf', () => {
    assert.equal(M.kindOf([]), 'template');
    assert.equal(M.kindOf(['sections', 1]), 'section');
    assert.equal(M.kindOf(['sections', 4, 'subsections', 0]), 'section');
    assert.equal(M.kindOf(['sections', 1, 'fields', 0]), 'field');
    assert.equal(M.kindOf(['sections', 2, 'step_groups', 0, 'steps', 1]), 'step');
    assert.deepEqual(M.sectionPathOf(['sections', 4, 'subsections', 0, 'fields', 2]), ['sections', 4, 'subsections', 0]);
});

test('slugify mirrors the server', () => {
    assert.equal(M.slugify('Pštrosí specifika'), 'pstrosi_specifika');
    assert.equal(M.slugify('  Fáze 1 – Ověření '), 'faze_1_overeni');
    assert.equal(M.slugify('!!!'), 'item');
});

test('placement rules', () => {
    const m = tpl();
    assert.ok(M.canDrop(m, 'section', ['sections'], {type: 'form'}));
    assert.ok(M.canDrop(m, 'field', ['sections', 1, 'fields']));
    assert.ok(!M.canDrop(m, 'field', ['sections', 3, 'fields']), 'no fields in a table');
    assert.ok(!M.canDrop(m, 'column', ['sections', 1, 'columns']), 'no columns in a form');
    assert.ok(M.canDrop(m, 'column', ['sections', 3, 'columns']));
    assert.ok(M.canDrop(m, 'step', ['sections', 2, 'steps']));
    assert.ok(M.canDrop(m, 'group', ['sections', 2, 'step_groups']));
    assert.ok(M.canDrop(m, 'section', ['sections', 4, 'subsections'], {type: 'table'}));
    assert.ok(!M.canDrop(m, 'section', ['sections', 4, 'subsections'], {type: 'header'}));
    assert.ok(!M.canDrop(m, 'section', ['sections', 4, 'subsections'], {type: 'section_group'}));
    assert.ok(!M.canDrop(m, 'field', ['sections']));
});

test('insert new items with unique ids/keys', () => {
    const m = tpl();
    const sec = M.newItem('section', 'form', m);
    assert.equal(sec.type, 'form');
    assert.ok(!M.sectionIds(m).includes(sec.id));
    M.insert(m, ['sections'], 1, sec);
    assert.equal(m.sections[1], sec);
    const f = M.newItem('field', 'select', m, m.sections[2].fields);
    assert.deepEqual(f.options, ['Option 1', 'Option 2']);
    const p = M.insert(m, ['sections', 2, 'fields'], null, f);
    assert.deepEqual(p, ['sections', 2, 'fields', 1]);
    const f2 = M.newItem('field', 'text', m, [{key: 'field_1'}]);
    assert.equal(f2.key, 'field_2');
    assert.ok(!('type' in f2), 'text is the default – not written');
});

test('move within a list and across lists', () => {
    const m = tpl();
    // field down inside header: index 0 → before index 3 (end)
    assert.deepEqual(M.move(m, ['sections', 0, 'fields', 0], ['sections', 0, 'fields'], 3), ['sections', 0, 'fields', 2]);
    assert.deepEqual(m.sections[0].fields.map(f => f.key), ['owner', 'title', 'record_id']);
    // field to another section
    assert.deepEqual(M.move(m, ['sections', 0, 'fields', 1], ['sections', 1, 'fields'], 0), ['sections', 1, 'fields', 0]);
    assert.deepEqual(m.sections[1].fields.map(f => f.key), ['title', 'a']);
    assert.deepEqual(m.sections[1].fields[0].custom_key, {a: 1}, 'unknown keys travel with the node');
    // top-level form into the group: target path shifts because an earlier sibling is removed
    const np = M.move(m, ['sections', 1], ['sections', 4, 'subsections'], 1);
    assert.deepEqual(np, ['sections', 3, 'subsections', 1]);
    assert.equal(M.get(m, np).id, 'form1');
    // not allowed: field into table, group into itself
    assert.equal(M.move(m, ['sections', 0, 'fields', 0], ['sections', 2, 'fields'], 0), null);
    assert.equal(M.move(m, ['sections', 3], ['sections', 3, 'subsections'], 0), null);
});

test('shift / duplicate / remove', () => {
    const m = tpl();
    assert.deepEqual(M.shift(m, ['sections', 1], -1), ['sections', 0]);
    assert.equal(m.sections[0].id, 'form1');
    assert.deepEqual(M.shift(m, ['sections', 0], -1), ['sections', 0], 'no-op at the edge');
    const dp = M.duplicate(m, ['sections', 0]);
    assert.equal(M.get(m, dp).id, 'form1_2');
    const fp = M.duplicate(m, ['sections', 0, 'fields', 0]);
    assert.equal(M.get(m, fp).key, 'a_2');
    M.remove(m, dp);
    assert.equal(m.sections.filter(s => s.id === 'form1_2').length, 0);
});

test('auto keeps the spelling the field already uses', () => {
    const m = tpl();
    const [short, long, plain] = m.sections[0].fields;
    assert.equal(M.getAuto(short), 'record_id');
    assert.equal(M.getAuto(long), 'current_user');
    M.setAuto(short, 'now'); assert.deepEqual(short, {key: 'record_id', label: 'ID', auto: 'now'});
    M.setAuto(long, 'now'); assert.equal(long.auto_value, 'now'); assert.ok(!('auto' in long));
    M.setAuto(long, ''); assert.ok(!('auto_value' in long) && !('editable' in long));
    M.setAuto(plain, 'meta.x'); assert.equal(plain.auto, 'meta.x');
    assert.ok(!M.isEditable(plain, 'field'));
});

test('setProp / setBool write only what is needed', () => {
    const f = {key: 'a', label: 'A', value: null};
    M.setProp(f, 'hint', 'x'); assert.equal(f.hint, 'x');
    M.setProp(f, 'hint', ''); assert.ok(!('hint' in f));
    M.setProp(f, 'value', '', {keepNull: true}); assert.equal(f.value, null);
    M.setBool(f, 'required', false, false); assert.ok(!('required' in f));
    M.setBool(f, 'required', true, false); assert.equal(f.required, true);
    M.setBool(f, 'required', false, false); assert.equal(f.required, false);
    M.setProp(f, '__proto__', {polluted: true}); assert.equal({}.polluted, undefined);
});

test('checklist: string steps and flat lists are preserved until they must change', () => {
    const m = tpl();
    const sec = m.sections[2];
    M.setStepProp(sec.steps, 0, 'action', 'ONE');
    assert.equal(sec.steps[0], 'ONE', 'still a plain string');
    M.setStepProp(sec.steps, 0, 'hint', '');
    assert.equal(sec.steps[0], 'ONE', 'empty attribute does not convert');
    M.setStepProp(sec.steps, 0, 'hint', 'why');
    assert.deepEqual(sec.steps[0], {action: 'ONE', hint: 'why'});
    assert.ok(M.isFlatChecklist(sec));
    const gp = M.insert(m, ['sections', 2, 'step_groups'], null, M.newItem('group'));
    assert.deepEqual(gp, ['sections', 2, 'step_groups', 1]);
    assert.deepEqual(Object.keys(sec), ['id', 'title', 'type', 'step_groups'], 'key position kept');
    assert.equal(sec.step_groups[0].title, null);
    assert.equal(sec.step_groups[0].steps.length, 2);
    assert.ok(M.canDrop(m, 'step', ['sections', 2, 'step_groups', 1, 'steps']));
    assert.ok(!M.canDrop(m, 'step', ['sections', 2, 'steps']));
    const sp = M.move(m, ['sections', 2, 'step_groups', 0, 'steps', 1], ['sections', 2, 'step_groups', 1, 'steps'], 0);
    assert.deepEqual(sp, ['sections', 2, 'step_groups', 1, 'steps', 0]);
});

test('otherKeys lists what the panel does not edit', () => {
    const m = tpl();
    assert.deepEqual(M.otherKeys(m.sections[0].fields[2], 'field'), ['custom_key']);
    assert.deepEqual(M.otherKeys({template_id: 'x', mitre_tactic: 'y', workflow: {}}, 'template'), ['mitre_tactic', 'workflow']);
});

test('sampleRecordId / buildCondition', () => {
    const d = new Date(Date.UTC(2026, 2, 16, 14, 23));
    assert.equal(M.sampleRecordId({prefix: 'UIB', format: '{prefix}-{DDMMYYYY}-{rand:04d}'}, d), 'UIB-16032026-0042');
    assert.equal(M.sampleRecordId({}, d), 'REC-202603-0042');
    assert.equal(M.buildCondition('src', '==', "Threat Intel"), "src == 'Threat Intel'");
    assert.equal(M.buildCondition('src', 'empty'), 'src == null');
    assert.equal(M.buildCondition('src', 'filled'), 'src != null');
});

test('untouched model survives a JSON round trip byte for byte', () => {
    const m = tpl();
    const before = JSON.stringify(m);
    M.walkSections(m, () => {});
    M.fieldKeys(m); M.sectionIds(m); M.otherKeys(m, 'template');
    assert.equal(JSON.stringify(M.clone(m)), before);
});

console.log(`\n${passed} tests passed`);
