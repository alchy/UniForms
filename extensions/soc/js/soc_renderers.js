/**
 * SOC Extension – Custom renderer registration
 *
 * ARCHITEKTURA:
 * Tento soubor je extension hook pro SOC workbooky.
 * Načítá se po core uniforms.js (definovaném v base.html) a po načtení
 * může registrovat vlastní typy sekcí přes UniForms.registerRenderer().
 *
 * AKTUÁLNÍ STAV (v2 šablony):
 * Všechny SOC sekce jsou nyní vykresleny universálními typy z uniforms.js:
 *
 *   classification  → type: form
 *     MITRE Tactic/Technique jako read-only (editable: false) textová pole
 *     Sub-technique jako editovatelný select
 *     Data sources jako read-only textarea (auto_value: meta.data_sources)
 *
 *   raci_table      → type: table (všechny sloupce editable: false)
 *     Legenda je v poli hint: na sekci
 *
 *   contact_table   → type: table (smíšená editovatelnost per-column)
 *   assets_table    → type: table (vše editable: true)
 *   action_table    → type: table (status sloupec editable: true, zbytek false)
 *
 * Tento soubor tedy aktuálně neregistruje žádné custom renderery.
 * Slouží jako dokumentovaný extension point pro budoucí SOC-specifické typy.
 *
 * JAK PŘIDAT CUSTOM RENDERER:
 * Pokud potřebuješ nový typ sekce specifický pro SOC (např. 'mitre_heatmap',
 * 'attack_timeline', 'ioc_table' s extra logikou), přidej ho níže takto:
 *
 *   UniForms.registerRenderer('nazev_typu', function renderMujTyp(section) {
 *       const { el, setHTML, buildTableHead } = UniForms._helpers;
 *       const wrap = el('div');
 *       // ... sestavení DOM ...
 *       return wrap;
 *   });
 *
 * Nový typ pak použij v YAML šabloně jako: type: nazev_typu
 *
 * DOSTUPNÉ HELPERS z UniForms._helpers:
 *   el(tag, css, html)         – vytvoří DOM element (html je sanitizován)
 *   setHTML(element, html)     – bezpečné innerHTML přiřazení
 *   sanitizeHTML(html)         – XSS sanitizace
 *   renderFieldRow(field)      – label + input řádek pro jedno pole
 *   renderFieldInput(field)    – input/select/textarea widget pro pole
 *   renderForm(fields)         – seznam field-row elementů
 *   renderInfoGrid(fields)     – kompaktní read-only info mřížka
 *   buildTableHead(cols, lbls) – <thead> pro tabulku
 *   buildOptions(sel, opts, v) – naplní <select> options
 *   makeDeleteBtn(onClick)     – tlačítko smazání řádku
 *   normalizeColumns(section)  – v1→v2 normalizace definice sloupců
 *   evalExpr(expr, fields)     – vyhodnotí visible_if / required_if výraz
 *   applyConditionals(fields, container) – naváže visible_if/required_if
 */

// Zde registruj custom renderery – viz příklady výše.
// Žádné custom renderery nejsou aktuálně potřeba (vše pokryto universálními typy).
