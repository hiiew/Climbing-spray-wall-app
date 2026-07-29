/**
 * api.js — Typed API client wrapping fetch
 *
 * All requests include the Sanctum CSRF cookie and Bearer token.
 * Errors are surfaced as { code, message } objects for easy handling.
 */

const BASE_URL = import.meta.env.VITE_API_URL ?? '/api/v1';

async function request(method, path, body = null, isMultipart = false) {
  const headers = { Accept: 'application/json' };

  const token = localStorage.getItem('auth_token');
  if (token) headers['Authorization'] = `Bearer ${token}`;

  if (!isMultipart && body) headers['Content-Type'] = 'application/json';

  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    credentials: 'same-origin',
    body: isMultipart ? body : (body ? JSON.stringify(body) : undefined),
  });

  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    const err = new Error(data?.error?.message ?? `HTTP ${res.status}`);
    err.code   = data?.error?.code ?? 'UNKNOWN';
    err.status = res.status;
    err.data   = data;
    throw err;
  }

  return data;
}

// ── Auth ──────────────────────────────────────────────────────────────────────
export const api = {
  auth: {
    login:    (email, password) => request('POST', '/auth/login', { email, password }),
    register: (payload)         => request('POST', '/auth/register', payload),
    logout:   ()                => request('POST', '/auth/logout'),
  },

  // ── Walls ──────────────────────────────────────────────────────────────────
  walls: {
    list:    ()       => request('GET', '/walls'),
    get:     (id)     => request('GET', `/walls/${id}`),
    delete:  (id)     => request('DELETE', `/walls/${id}`),

    create: (formData, onProgress) => {
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        const token = localStorage.getItem('auth_token');

        xhr.open('POST', `${BASE_URL}/walls`);
        xhr.setRequestHeader('Accept', 'application/json');
        if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);

        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable && onProgress) {
            onProgress(Math.round((e.loaded / e.total) * 100));
          }
        };

        xhr.onload = () => {
          const data = JSON.parse(xhr.responseText);
          if (xhr.status >= 200 && xhr.status < 300) { resolve(data); }
          else {
            const err = new Error(data?.error?.message ?? `HTTP ${xhr.status}`);
            err.code = data?.error?.code ?? 'UNKNOWN'; err.data = data;
            reject(err);
          }
        };

        xhr.onerror = () => reject(new Error('Network error during upload'));
        xhr.send(formData);
      });
    },
  },

  // ── Holds ──────────────────────────────────────────────────────────────────
  holds: {
    list:   (wallId)         => request('GET', `/walls/${wallId}/holds`),
    update: (holdId, body)   => request('PATCH', `/holds/${holdId}`, body),
    delete: (holdId)         => request('DELETE', `/holds/${holdId}`),
  },

  // ── Routes ─────────────────────────────────────────────────────────────────
  routes: {
    generate: (wallId, params) => request('POST', `/walls/${wallId}/routes/generate`, params),
    get:      (routeId)        => request('GET', `/routes/${routeId}`),
    save:     (routeId, body)  => request('PATCH', `/routes/${routeId}`, body),
    delete:   (routeId)        => request('DELETE', `/routes/${routeId}`),
    rate:     (routeId, stars) => request('POST', `/routes/${routeId}/ratings`, { stars }),
    comment:  (routeId, body)  => request('POST', `/routes/${routeId}/comments`, { body }),
    share:    (token)          => request('GET', `/share/${token}`),
  },
};
