/**
 * UniForms – main JavaScript utilities
 *
 * Shared API fetch helper and utilities used across all pages.
 * Page-specific logic lives inline in Jinja2 templates.
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
