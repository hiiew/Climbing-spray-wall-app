/**
 * Toast/index.jsx — Real-time notification system
 *
 * Renders a stack of toast notifications in the bottom-right corner.
 * Auto-dismisses after 5s. Supports: success | error | info | warning.
 * Accessible: aria-live="polite/assertive" based on severity.
 */

import React, { useCallback } from 'react';
import { useWallStore } from '../../hooks/useWallStore';
import './Toast.css';

const TOAST_CONFIG = {
  success: { icon: '✓', label: 'Success', live: 'polite',    accent: 'var(--accent-green)'  },
  error:   { icon: '✕', label: 'Error',   live: 'assertive', accent: 'var(--accent-red)'    },
  warning: { icon: '⚠', label: 'Warning', live: 'polite',    accent: 'var(--accent-yellow)' },
  info:    { icon: 'ℹ', label: 'Info',    live: 'polite',    accent: 'var(--accent-blue)'   },
};

function ToastItem({ notification, onDismiss }) {
  const config = TOAST_CONFIG[notification.type] ?? TOAST_CONFIG.info;

  return (
    <div
      className={`toast toast-${notification.type}`}
      role="status"
      aria-live={config.live}
      aria-atomic="true"
      aria-label={`${config.label}: ${notification.message}`}
      style={{ '--toast-accent': config.accent }}
    >
      <span className="toast-icon" aria-hidden="true">{config.icon}</span>
      <span className="toast-message">{notification.message}</span>
      <button
        type="button"
        className="toast-dismiss"
        onClick={() => onDismiss(notification.id)}
        aria-label={`Dismiss ${config.label.toLowerCase()} notification`}
      >
        ✕
      </button>
      <div className="toast-progress" aria-hidden="true" />
    </div>
  );
}

export default function ToastContainer() {
  const { notifications, removeNotification } = useWallStore();

  const handleDismiss = useCallback((id) => {
    removeNotification(id);
  }, [removeNotification]);

  if (!notifications.length) return null;

  return (
    <div
      className="toast-container"
      aria-label="Notifications"
      aria-live="polite"
    >
      {notifications.map((n) => (
        <ToastItem key={n.id} notification={n} onDismiss={handleDismiss} />
      ))}
    </div>
  );
}
