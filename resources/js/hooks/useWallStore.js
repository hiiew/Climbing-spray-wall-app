/**
 * useWallStore.js — Zustand global state store
 *
 * Central state for the wall detail page. Manages:
 * - Wall metadata and scan status
 * - Detected holds and their selection state
 * - Generated route data
 * - UI state (loading, panels, modals)
 */

import { create } from 'zustand';
import { devtools } from 'zustand/middleware';

const ROLE_COLORS = {
  start:  { fill: '#22C55E', stroke: '#16A34A', label: 'Start' },
  hand:   { fill: '#3B82F6', stroke: '#2563EB', label: 'Hand' },
  foot:   { fill: '#EAB308', stroke: '#CA8A04', label: 'Foot' },
  finish: { fill: '#EF4444', stroke: '#DC2626', label: 'Finish' },
};

const DEFAULT_HOLD_COLOR = { fill: 'rgba(255,255,255,0.25)', stroke: 'rgba(255,255,255,0.5)' };
const EXCLUDED_COLOR     = { fill: 'rgba(255,255,255,0.06)', stroke: 'rgba(255,255,255,0.15)' };

export const useWallStore = create(
  devtools(
    (set, get) => ({
      // ── Wall ───────────────────────────────────────────────────────────────
      wall:           null,
      scanStatus:     'idle',   // idle | uploading | pending_scan | scanning | scan_complete | scan_failed

      // ── Holds ──────────────────────────────────────────────────────────────
      holds:          [],
      excludedHolds:  new Set(),  // Set of hold IDs excluded by user

      // ── Route ──────────────────────────────────────────────────────────────
      currentRoute:   null,       // { id, grade, style, holds: [{ hold_id, role, position_order }] }
      routeHoldMap:   {},         // { [hold_id]: { role, position_order } }

      // ── UI ─────────────────────────────────────────────────────────────────
      uploadProgress:     0,
      isGenerating:       false,
      isSaveModalOpen:    false,
      isHoldDetailOpen:   false,
      selectedHold:       null,
      notifications:      [],     // [{ id, type, message }]

      // ── Wall actions ────────────────────────────────────────────────────────
      setWall: (wall) => set({ wall, scanStatus: wall?.status ?? 'idle' }),
      setScanStatus: (status) => set({ scanStatus: status }),
      setUploadProgress: (progress) => set({ uploadProgress: progress }),

      // ── Hold actions ────────────────────────────────────────────────────────
      setHolds: (holds) => set({ holds }),

      toggleHoldExclusion: (holdId) => set((state) => {
        const next = new Set(state.excludedHolds);
        if (next.has(holdId)) { next.delete(holdId); }
        else                   { next.add(holdId); }
        return { excludedHolds: next };
      }),

      setSelectedHold: (hold) => set({ selectedHold: hold, isHoldDetailOpen: !!hold }),

      // ── Route actions ───────────────────────────────────────────────────────
      setCurrentRoute: (route) => {
        if (!route) {
          set({ currentRoute: null, routeHoldMap: {} });
          return;
        }
        const map = {};
        route.holds.forEach((h) => { map[h.hold_id] = h; });
        set({ currentRoute: route, routeHoldMap: map });
      },

      clearRoute: () => set({ currentRoute: null, routeHoldMap: {} }),

      // ── UI actions ──────────────────────────────────────────────────────────
      setGenerating: (v) => set({ isGenerating: v }),
      openSaveModal:  () => set({ isSaveModalOpen: true }),
      closeSaveModal: () => set({ isSaveModalOpen: false }),

      addNotification: (type, message) => {
        const id = Date.now() + Math.random();
        set((state) => ({
          notifications: [...state.notifications, { id, type, message }],
        }));
        setTimeout(() => get().removeNotification(id), 5000);
        return id;
      },

      removeNotification: (id) =>
        set((state) => ({ notifications: state.notifications.filter((n) => n.id !== id) })),

      // ── Computed helpers (not reactive — call inside components) ────────────
      getHoldDisplayProps: (holdId) => {
        const { excludedHolds, routeHoldMap, currentRoute } = get();
        if (excludedHolds.has(holdId)) return { ...EXCLUDED_COLOR, isExcluded: true };
        if (currentRoute && routeHoldMap[holdId]) {
          const role = routeHoldMap[holdId].role;
          return { ...ROLE_COLORS[role], isInRoute: true, role };
        }
        return { ...DEFAULT_HOLD_COLOR, isDefault: true };
      },
    }),
    { name: 'WallStore' }
  )
);

export { ROLE_COLORS };
