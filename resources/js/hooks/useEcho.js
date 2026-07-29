/**
 * useEcho.js — Laravel Echo / WebSocket hook
 *
 * Listens on the authenticated user's private channel for:
 *   - WallScanComplete  → updates hold map, shows success toast
 *   - WallScanFailed    → shows error toast
 *   - RouteGenerated    → future extension
 *
 * Requires: laravel-echo, pusher-js installed as npm deps.
 */

import { useEffect, useRef } from 'react';
import Echo from 'laravel-echo';
import Pusher from 'pusher-js';
import { useWallStore } from './useWallStore';

// Initialise Echo once (module-level singleton)
let echoInstance = null;

function getEcho() {
  if (echoInstance) return echoInstance;

  window.Pusher = Pusher;
  echoInstance = new Echo({
    broadcaster:   'pusher',
    key:            import.meta.env.VITE_PUSHER_APP_KEY,
    cluster:        import.meta.env.VITE_PUSHER_APP_CLUSTER ?? 'mt1',
    wsHost:         import.meta.env.VITE_PUSHER_HOST ?? `ws-${import.meta.env.VITE_PUSHER_APP_CLUSTER}.pusher.com`,
    wsPort:         import.meta.env.VITE_PUSHER_PORT ?? 80,
    wssPort:        import.meta.env.VITE_PUSHER_PORT ?? 443,
    forceTLS:       import.meta.env.VITE_PUSHER_SCHEME === 'https',
    enabledTransports: ['ws', 'wss'],
    authEndpoint:   '/broadcasting/auth',
  });

  return echoInstance;
}

/**
 * @param {number|null} userId  - Authenticated user ID (null = not listening)
 * @param {string|null} wallId  - Current wall ID being watched
 * @param {function}    onHoldsDetected - Callback: (wallId, holdCount) => void
 * @param {function}    onScanFailed    - Callback: (wallId, reason) => void
 */
export function useEcho({ userId, wallId, onHoldsDetected, onScanFailed }) {
  const channelRef = useRef(null);
  const { addNotification, setScanStatus } = useWallStore();

  useEffect(() => {
    if (!userId) return;

    const echo    = getEcho();
    const channel = echo.private(`user.${userId}`);
    channelRef.current = channel;

    channel.listen('.WallScanComplete', (data) => {
      if (wallId && data.wall_id !== wallId) return;

      setScanStatus('scan_complete');
      addNotification('success', `🎉 Wall scan complete — ${data.hold_count} holds detected!`);
      onHoldsDetected?.(data.wall_id, data.hold_count);
    });

    channel.listen('.WallScanFailed', (data) => {
      if (wallId && data.wall_id !== wallId) return;

      setScanStatus('scan_failed');
      addNotification('error', `Scan failed: ${data.reason}`);
      onScanFailed?.(data.wall_id, data.reason);
    });

    return () => {
      channel.stopListening('.WallScanComplete');
      channel.stopListening('.WallScanFailed');
    };
  }, [userId, wallId]);
}
