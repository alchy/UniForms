/**
 * UniForms – Collection Designer model operations
 *
 * Pure functions (no DOM) that edit the designer *model*: the plain object a
 * collection / template YAML file parses to. The model is NOT normalized –
 * shorthand such as `auto:`, `example:`, flat `steps:` or string steps stays
 * exactly as written, and keys the designer has no control for are never
 * touched. That is what keeps a load → edit → save round trip lossless.
 *
 * Nodes are addressed by a path – an array of keys / indexes from the model
 * root, e.g. ['sections', 2, 'fields', 0]. The kind of a node follows from the
 * list it lives in:
 *
 *   sections / subsections → 'section'      fields  → 'field'
 *   columns                → 'column'       steps   → 'step'
 *   step_groups            → 'group'
 *
 * Exposed as the single global `DesignerModel` (and as a CommonJS module so
 * the same code is unit-tested under node).
 */
(function (root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    else root.DesignerModel = api;
})(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    const LIST_KINDS = {
        sections: 'section', subsections: 'section', fields: 'field',
        columns: 'column', step_groups: 'group', steps: 'step',
    };
    const FORBIDDEN_KEYS = new Set(['__proto__', 'constructor', 'prototype']);

    // Keys the attribute panel has a control for; everything else is shown as
    // "other attributes" and preserved untouched.
    const KNOWN_KEYS = {
        template: ['template_id', 'name', 'version', 'category', 'status', 'description',
                   'abstract', 'extends', 'meta', 'sections'],
        section: ['override', 'remove', 'use', 'id', 'title', 'type', 'description', 'hint', 'note', 'always_expanded',
                  'fields', 'columns', 'rows', 'append_row_template', 'allow_append_row',
                  'allow_delete_row', 'steps', 'step_groups', 'subsections'],
        field: ['key', 'label', 'type', 'options', 'source', 'display_tz', 'editable', 'required', 'auto', 'auto_value',
                'placeholder', 'hint', 'example', 'value', 'visible_if', 'required_if'],
        column: ['key', 'label', 'type', 'options', 'display_tz', 'editable'],
        group: ['id', 'title', 'note', 'hints', 'steps'],
        step: ['id', 'action', 'hint', 'example'],
    };

    function clone(value) {
        return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
    }

    function isObject(value) {
        return value !== null && typeof value === 'object' && !Array.isArray(value);
    }

    /** Mirror of the server's _slugify(): ASCII, lower case, words joined by '_'. */
    function slugify(text) {
        let s = String(text == null ? '' : text).normalize('NFD').replace(/[^\x00-\x7f]/g, '');
        s = s.toLowerCase().trim().replace(/[^\w\s-]/g, '').replace(/[\s-]+/g, '_');
        return s || 'item';
    }

    function get(model, path) {
        let node = model;
        for (const key of path) {
            if (node === null || node === undefined) return undefined;
            node = node[key];
        }
        return node;
    }

    function pathEquals(a, b) {
        return !!a && !!b && a.length === b.length && a.every((k, i) => k === b[i]);
    }

    function isPrefix(prefix, path) {
        return prefix.length <= path.length && prefix.every((k, i) => k === path[i]);
    }

    /** Kind of the node at `path` ('template' for the root). */
    function kindOf(path) {
        if (!path || path.length === 0) return 'template';
        return LIST_KINDS[path[path.length - 2]] || null;
    }

    function listKind(listPath) {
        return LIST_KINDS[listPath[listPath.length - 1]] || null;
    }

    /** Path of the section that owns the node at `path` (the node itself if it is a section). */
    function sectionPathOf(path) {
        for (let i = path.length; i >= 2; i--) {
            if (LIST_KINDS[path[i - 2]] === 'section') return path.slice(0, i);
        }
        return null;
    }

    /** Set or remove a text-like property. Empty values remove the key (keeps the YAML terse). */
    function setProp(obj, key, value, opts) {
        if (!isObject(obj) || FORBIDDEN_KEYS.has(key)) return;
        const empty = value === '' || value === null || value === undefined ||
            (Array.isArray(value) && value.length === 0);
        if (empty) {
            if (opts && opts.keepNull && key in obj) obj[key] = null;
            else delete obj[key];
        } else {
            obj[key] = value;
        }
    }

    /** Set a boolean; a value equal to the default is not written unless the key already exists. */
    function setBool(obj, key, value, dflt) {
        if (!isObject(obj) || FORBIDDEN_KEYS.has(key)) return;
        if (value === dflt && !(key in obj)) return;
        obj[key] = !!value;
    }

    /** Replace key `oldKey` by `newKey` keeping its position among the object's keys. */
    function renameKey(obj, oldKey, newKey, newValue) {
        if (FORBIDDEN_KEYS.has(newKey)) return;
        const entries = Object.entries(obj);
        for (const k of Object.keys(obj)) delete obj[k];
        for (const [k, v] of entries) {
            if (k === oldKey) obj[newKey] = newValue;
            else if (k !== newKey) obj[k] = v;
        }
    }

    function uniqueName(existing, base) {
        const taken = new Set(existing);
        if (!taken.has(base)) return base;
        const stem = base.replace(/_\d+$/, '');
        for (let i = 2; ; i++) {
            const candidate = `${stem}_${i}`;
            if (!taken.has(candidate)) return candidate;
        }
    }

    // ── Sections / fields discovery ─────────────────────────────────────────

    /** Every section of a template incl. section_group children, with its path. */
    function walkSections(model, visit, base) {
        const list = base ? get(model, base) : model.sections;
        const basePath = base || ['sections'];
        (Array.isArray(list) ? list : []).forEach((sec, i) => {
            if (!isObject(sec)) return;
            const path = basePath.concat(i);
            visit(sec, path);
            if (Array.isArray(sec.subsections)) walkSections(model, visit, path.concat('subsections'));
        });
    }

    function sectionIds(model) {
        const ids = [];
        walkSections(model, sec => { if (sec.id) ids.push(String(sec.id)); });
        return ids;
    }

    function fieldKeys(model) {
        const keys = [];
        walkSections(model, sec => {
            (Array.isArray(sec.fields) ? sec.fields : []).forEach(f => {
                if (isObject(f) && typeof f.key === 'string') keys.push(f.key);
            });
        });
        return keys;
    }

    // ── Field helpers ───────────────────────────────────────────────────────

    /** Automatic value source of a field – shorthand `auto` or the long `auto_value`. */
    function getAuto(field) {
        if (!isObject(field)) return '';
        if (field.auto !== undefined && field.auto !== null) return String(field.auto);
        if (field.auto_value !== undefined && field.auto_value !== null) return String(field.auto_value);
        return '';
    }

    /** Set / clear the automatic value, keeping whichever spelling the field already uses. */
    function setAuto(field, source) {
        if (!isObject(field)) return;
        if (!source) {
            const hadLong = 'auto_value' in field;
            delete field.auto;
            delete field.auto_value;
            if (hadLong && field.editable === false) delete field.editable;
            return;
        }
        if ('auto_value' in field && !('auto' in field)) {
            field.auto_value = source;
            field.editable = false;
        } else {
            field.auto = source;
        }
    }

    function isEditable(node, kind) {
        if (kind === 'column') return node.editable === true;
        if (getAuto(node)) return false;
        return node.editable !== false;
    }

    // ── Checklist helpers ───────────────────────────────────────────────────

    function isFlatChecklist(section) {
        return isObject(section) && Array.isArray(section.steps) && !('step_groups' in section);
    }

    /** Turn flat `steps:` into `step_groups:` with one untitled group (same meaning). */
    function convertToGroups(section) {
        if ('step_groups' in section) return;
        if ('steps' in section) {
            renameKey(section, 'steps', 'step_groups', [{title: null, steps: section.steps}]);
        } else {
            section.step_groups = [];
        }
    }

    function stepAction(step) {
        return typeof step === 'string' ? step : (isObject(step) && step.action != null ? String(step.action) : '');
    }

    /** Set a property of a step; a plain-text step becomes a mapping only when it needs to. */
    function setStepProp(steps, index, key, value) {
        const step = steps[index];
        if (typeof step === 'string') {
            if (key === 'action') { steps[index] = String(value == null ? '' : value); return; }
            const obj = {action: step};
            if (typeof value === 'boolean') setBool(obj, key, value, false);
            else setProp(obj, key, value);
            if (Object.keys(obj).length > 1) steps[index] = obj;
            return;
        }
        if (!isObject(step)) return;
        if (key === 'action') step.action = String(value == null ? '' : value);
        else if (typeof value === 'boolean') setBool(step, key, value, false);
        else setProp(step, key, value);
    }

    // ── Creating nodes ──────────────────────────────────────────────────────

    const SECTION_DEFAULTS = {
        header: () => ({title: 'Header', type: 'header', fields: []}),
        form: () => ({title: 'New form', type: 'form', fields: []}),
        checklist: () => ({title: 'New checklist', type: 'checklist', steps: []}),
        table: () => ({title: 'New table', type: 'table', allow_append_row: true,
                       allow_delete_row: true, columns: []}),
        section_group: () => ({title: 'New group', type: 'section_group', subsections: []}),
    };

    /**
     * Build a new node of `kind` ('section' | 'field' | 'column' | 'group' | 'step').
     * `type` is the section / field type ('auto' creates an automatic field).
     * `model` and `siblings` are used to pick an id / key that is not taken yet.
     */
    function newItem(kind, type, model, siblings) {
        const sibs = Array.isArray(siblings) ? siblings : [];
        if (kind === 'section') {
            // a building block from a library: live reference '<template_id>#<section id>'
            if (typeof type === 'string' && type.startsWith('use:')) return {use: type.slice(4)};
            const make = SECTION_DEFAULTS[type] || (() => ({title: 'New section', type}));
            const sec = make();
            const id = uniqueName(sectionIds(model || {}), type === 'header' ? 'header' : slugify(sec.title));
            return Object.assign({id}, sec);
        }
        if (kind === 'field') {
            const keys = sibs.filter(isObject).map(f => f.key);
            if (type === 'auto') {
                return {key: uniqueName(keys, 'record_id'), label: 'Record ID', auto: 'record_id'};
            }
            if (type === 'record_owner') {
                return {key: uniqueName(keys, 'record_owner'), label: 'Record owner', type: 'user',
                        source: 'collection_members', hint: 'Filled by the Take over button.'};
            }
            if (type === 'user') {
                return {key: uniqueName(keys, 'user_1'), label: 'User', type: 'user', source: 'collection_members'};
            }
            const field = {key: uniqueName(keys, 'field_1'), label: 'New field'};
            if (type && type !== 'text') field.type = type;
            if (type === 'select') field.options = ['Option 1', 'Option 2'];
            return field;
        }
        if (kind === 'column') {
            const keys = sibs.filter(isObject).map(c => c.key);
            const col = {key: uniqueName(keys, 'column_1'), label: 'New column', type: type || 'text', editable: true};
            if (type === 'select') col.options = ['Option 1', 'Option 2'];
            return col;
        }
        if (kind === 'group') return {title: 'New group', steps: []};
        if (kind === 'step') return 'New step';
        return null;
    }

    // ── Structure operations ────────────────────────────────────────────────

    /**
     * May a node of `kind` be placed into the list at `listPath`?
     * `item` (optional) is the node itself – section types have placement rules.
     */
    function canDrop(model, kind, listPath, item) {
        const key = listPath[listPath.length - 1];
        if (LIST_KINDS[key] !== kind) return false;
        const owner = get(model, listPath.slice(0, -1));
        if (listPath.length === 1) return key === 'sections' && kind === 'section';
        if (!isObject(owner)) return false;
        const type = owner.type;
        if (kind === 'section') {
            if (key !== 'subsections' || type !== 'section_group') return false;
            const itemType = isObject(item) ? item.type : null;
            if (isObject(item) && (item.use || (typeof itemType === 'string' && itemType.startsWith('use:')))) return false;
            return itemType !== 'header' && itemType !== 'section_group';
        }
        if (kind === 'field') return type === 'header' || type === 'form' || Array.isArray(owner.fields);
        if (kind === 'column') {
            const cols = owner.columns;
            const legacy = Array.isArray(cols) && cols.length > 0 && typeof cols[0] === 'string';
            return type === 'table' && !legacy;
        }
        if (kind === 'group') return type === 'checklist' && kindOf(listPath.slice(0, -1)) === 'section';
        if (kind === 'step') {
            if (key !== 'steps') return false;
            if (type === 'checklist') return !('step_groups' in owner);       // flat checklist
            return kindOf(listPath.slice(0, -1)) === 'group';                 // inside a step group
        }
        return false;
    }

    /** Return the list at `listPath`, creating it when missing (flat checklists are converted). */
    function ensureList(model, listPath) {
        const owner = get(model, listPath.slice(0, -1));
        const key = listPath[listPath.length - 1];
        if (!isObject(owner)) return null;
        if (key === 'step_groups' && !('step_groups' in owner)) convertToGroups(owner);
        if (!Array.isArray(owner[key])) owner[key] = [];
        return owner[key];
    }

    /** Insert `item` at `index` (clamped) of the list at `listPath`; returns the new node path. */
    function insert(model, listPath, index, item) {
        const list = ensureList(model, listPath);
        if (!list) return null;
        const at = Math.max(0, Math.min(index == null ? list.length : index, list.length));
        list.splice(at, 0, item);
        return listPath.concat(at);
    }

    function remove(model, path) {
        const list = get(model, path.slice(0, -1));
        if (!Array.isArray(list)) return undefined;
        return list.splice(path[path.length - 1], 1)[0];
    }

    /**
     * Move the node at `fromPath` to position `toIndex` of the list at `toListPath`.
     * Returns the node's new path, or null when the move is not allowed.
     */
    function move(model, fromPath, toListPath, toIndex) {
        const kind = kindOf(fromPath);
        const item = get(model, fromPath);
        if (item === undefined || !canDrop(model, kind, toListPath, item)) return null;
        if (isPrefix(fromPath, toListPath)) return null;            // into its own subtree
        const fromListPath = fromPath.slice(0, -1);
        const fromList = get(model, fromListPath);
        const toList = ensureList(model, toListPath);               // resolve before removal shifts indexes
        if (!Array.isArray(fromList) || !toList) return null;
        const fromIndex = fromPath[fromPath.length - 1];
        let at = Math.max(0, Math.min(toIndex == null ? toList.length : toIndex, toList.length));
        if (fromList === toList && fromIndex < at) at -= 1;
        fromList.splice(fromIndex, 1);
        toList.splice(at, 0, item);
        // Removing an earlier sibling of an ancestor shifts the target path by one
        const newListPath = toListPath.slice();
        if (fromList !== toList && isPrefix(fromListPath, toListPath)
            && typeof toListPath[fromListPath.length] === 'number'
            && toListPath[fromListPath.length] > fromIndex) {
            newListPath[fromListPath.length] -= 1;
        }
        return newListPath.concat(at);
    }

    /** Move a node one step up (-1) or down (+1) within its list. Returns the new path. */
    function shift(model, path, delta) {
        const list = get(model, path.slice(0, -1));
        const i = path[path.length - 1];
        const j = i + delta;
        if (!Array.isArray(list) || j < 0 || j >= list.length) return path;
        list.splice(j, 0, list.splice(i, 1)[0]);
        return path.slice(0, -1).concat(j);
    }

    /** Duplicate a node next to itself with a fresh id / key. Returns the copy's path. */
    function duplicate(model, path) {
        const list = get(model, path.slice(0, -1));
        const kind = kindOf(path);
        if (!Array.isArray(list)) return null;
        const copy = clone(list[path[path.length - 1]]);
        if (isObject(copy)) {
            if (kind === 'section') {
                const taken = sectionIds(model);
                const rename = sec => {
                    if (sec.id) { sec.id = uniqueName(taken, String(sec.id)); taken.push(sec.id); }
                    (Array.isArray(sec.subsections) ? sec.subsections : []).filter(isObject).forEach(rename);
                };
                rename(copy);
            } else if (kind === 'field' || kind === 'column') {
                if (copy.key) copy.key = uniqueName(list.filter(isObject).map(n => n.key), String(copy.key));
            } else if (kind === 'group' && copy.id) {
                copy.id = uniqueName(list.filter(isObject).map(n => n.id), String(copy.id));
            } else if (kind === 'step') {
                delete copy.id;
            }
        }
        list.splice(path[path.length - 1] + 1, 0, copy);
        return path.slice(0, -1).concat(path[path.length - 1] + 1);
    }

    /** Keys of `node` the attribute panel has no control for (shown read-only, preserved). */
    function otherKeys(node, kind) {
        if (!isObject(node)) return [];
        const known = new Set(KNOWN_KEYS[kind] || []);
        return Object.keys(node).filter(k => !known.has(k));
    }

    // ── Collection helpers ──────────────────────────────────────────────────

    /** Sample record ID for an id_format – mirrors record_service.generate_record_id(). */
    function sampleRecordId(idFormat, now) {
        const fmt = (idFormat && idFormat.format) || '{prefix}-{YYYYMM}-{rand:04d}';
        const prefix = idFormat && idFormat.prefix != null ? String(idFormat.prefix) : 'REC';
        const d = now || new Date();
        const p2 = n => String(n).padStart(2, '0');
        const Y = String(d.getUTCFullYear()), Mo = p2(d.getUTCMonth() + 1), D = p2(d.getUTCDate());
        const tokens = [
            ['{prefix}', prefix], ['{DDMMYYYY}', D + Mo + Y], ['{YYYYMM}', Y + Mo], ['{YYYY}', Y],
            ['{MM}', Mo], ['{DD}', D], ['{HHMM}', p2(d.getUTCHours()) + p2(d.getUTCMinutes())],
            ['{rand:04d}', '0042'], ['{rand}', '42'],
        ];
        return tokens.reduce((out, [token, value]) => out.split(token).join(value), String(fmt));
    }

    /** Build a visible_if / required_if expression from the condition builder inputs. */
    function buildCondition(fieldKey, op, value) {
        if (!fieldKey) return '';
        if (op === 'empty') return `${fieldKey} == null`;
        if (op === 'filled') return `${fieldKey} != null`;
        const quoted = `'${String(value == null ? '' : value).replace(/'/g, '')}'`;
        return `${fieldKey} ${op === '!=' ? '!=' : '=='} ${quoted}`;
    }

    return {
        LIST_KINDS, KNOWN_KEYS,
        clone, isObject, slugify, get, pathEquals, isPrefix, kindOf, listKind, sectionPathOf,
        setProp, setBool, renameKey, uniqueName,
        walkSections, sectionIds, fieldKeys,
        getAuto, setAuto, isEditable,
        isFlatChecklist, convertToGroups, stepAction, setStepProp,
        newItem, canDrop, ensureList, insert, remove, move, shift, duplicate, otherKeys,
        sampleRecordId, buildCondition,
    };
});
