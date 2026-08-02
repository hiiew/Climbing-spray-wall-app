/**
 * app.jsx — React application entry point
 *
 * Mounts the React app. If using Inertia.js, swap the ReactDOM.render
 * block with the createInertiaApp call shown in the comment below.
 */

import React from 'react';
import ReactDOM from 'react-dom/client';
import '../css/index.css';
import WallDetail from './pages/WallDetail';

// ── Standalone React mount (non-Inertia) ─────────────────────────────────
const rootEl = document.getElementById('root');
if (rootEl) {
  // Read props from the HTML data attributes (set by Blade template)
  const initialWall = rootEl.dataset.wall   ? JSON.parse(rootEl.dataset.wall)  : null;
  const user        = rootEl.dataset.user   ? JSON.parse(rootEl.dataset.user)  : null;

  ReactDOM.createRoot(rootEl).render(
    <React.StrictMode>
      <WallDetail initialWall={initialWall} user={user} />
    </React.StrictMode>
  );
}

/* ── If using Inertia.js instead, replace above with: ──────────────────────

import { createInertiaApp } from '@inertiajs/react';
import { resolvePageComponent } from 'laravel-vite-plugin/inertia-helpers';

createInertiaApp({
  title:   (title) => `${title} — SprayWall`,
  resolve: (name) =>
    resolvePageComponent(`./pages/${name}.jsx`, import.meta.glob('./pages/** /*.jsx')),
  setup({ el, App, props }) {
    ReactDOM.createRoot(el).render(<App {...props} />);
  },
});

─────────────────────────────────────────────────────────────────────────── */
