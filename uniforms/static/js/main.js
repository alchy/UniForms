/**
 * UniForms – main JavaScript utilities
 *
 * Shared helpers used across all pages (loaded from base.html):
 *   apiFetch()   – authenticated fetch wrapper
 *   escapeHtml() – HTML escaping for values interpolated into innerHTML
 *   badgeAttrs() – workflow state color → badge CSS classes / inline style
 *   showToast()  – bottom-right Bootstrap toast
 *
 * Page-specific logic lives in dedicated files (records_list.js,
 * record_detail.js) or inline in the Jinja2 template.
 */

/**
 * Authenticated fetch wrapper.
 * Cookie is sent automatically (same-origin credentials).
 * Automatically redirects to /login on 401.
 *
 * @param {string} url
 * @param {RequestInit} options
 * @returns {Promise<Response>}
 */
async function apiFetch(url, options = {}) {
    const defaults = {
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            ...options.headers,
        },
    };
    const response = await fetch(url, {...defaults, ...options});

    if (response.status === 401) {
        window.location.href = '/login';
        return response;
    }

    return response;
}

/**
 * Escape a value for safe interpolation into innerHTML.
 * Use for ANY user-editable data (field values, usernames, labels).
 */
function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

/**
 * Map a workflow state color to badge presentation.
 * Bootstrap variant names use utility classes; any other value is treated
 * as a raw CSS color and rendered via color-mix inline styles.
 *
 * @param {string} color
 * @returns {{cls: string, style: string, iconCls: string, iconStyle: string}}
 */
const _BS_COLORS = new Set(['secondary', 'primary', 'warning', 'success', 'info', 'danger', 'dark']);
function badgeAttrs(color) {
    if (color && _BS_COLORS.has(color)) {
        return {
            cls: `bg-${color}-subtle text-${color} border border-${color}-subtle`,
            style: '',
            iconCls: `text-${color}`,
            iconStyle: '',
        };
    }
    const raw = color || 'secondary';
    return {
        cls: 'border',
        style: `background-color:color-mix(in srgb,${raw} 12%,white);color:${raw};border-color:color-mix(in srgb,${raw} 35%,transparent)`,
        iconCls: '',
        iconStyle: `color:${raw}`,
    };
}

/**
 * Show a transient Bootstrap toast in the bottom-right corner.
 *
 * @param {string} msg  – plain text message (escaped)
 * @param {string} type – Bootstrap color variant (success, danger, …)
 */
function showToast(msg, type = 'success') {
    const t = document.createElement('div');
    t.className = `toast align-items-center text-bg-${type} border-0 show position-fixed bottom-0 end-0 m-3`;
    t.style.zIndex = 9999;
    t.innerHTML = `<div class="d-flex"><div class="toast-body">${escapeHtml(msg)}</div>
      <button type="button" class="btn-close btn-close-white me-2 m-auto" onclick="this.parentElement.parentElement.remove()"></button></div>`;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 3000);
}
