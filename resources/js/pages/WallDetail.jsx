/**
 * WallDetail.jsx — Main wall page
 *
 * Assembles all components into the full spray wall experience:
 * ┌─────────────────────────────────────────────────────┬──────────────────┐
 * │  Wall Image + HoldMapOverlay (SVG)                  │  RouteGenerator  │
 * │                                                     │  Panel           │
 * │  [Scan status banner if scanning]                   │                  │
 * └─────────────────────────────────────────────────────┴──────────────────┘
 *
 * Receives wall data via props (passed from Inertia page or router).
 * Manages WebSocket subscription and hold loading lifecycle.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import HoldMapOverlay from '../components/HoldMapOverlay';
import RouteGeneratorPanel from '../components/RouteGeneratorPanel';
import SaveRouteModal from '../components/SaveRouteModal';
import ToastContainer from '../components/Toast';
import WallUploader from '../components/WallUploader';
import { useEcho } from '../hooks/useEcho';
import { useWallStore } from '../hooks/useWallStore';
import './WallDetail.css';

export default function WallDetail({ initialWall = null, user = null }) {
  const [showUploader, setShowUploader] = useState(!initialWall);

  const {
    wall, scanStatus, holds,
    setWall, setHolds, setScanStatus, addNotification,
  } = useWallStore();

  /* Sync initial wall on mount */
  useEffect(() => {
    if (initialWall) {
      setWall(initialWall);
      if (initialWall.status === 'scan_complete') {
        loadHolds(initialWall.id);
      }
    }
  }, []);

  /* Load holds from API */
  const loadHolds = useCallback(async (wallId) => {
    try {
      const response = await api.holds.list(wallId);
      setHolds(response.data ?? []);
    } catch (err) {
      addNotification('error', 'Failed to load holds: ' + (err.message ?? 'Unknown error'));
    }
  }, [setHolds, addNotification]);

  /* WebSocket: scan completion → reload holds */
  useEcho({
    userId: user?.id,
    wallId: wall?.id,
    onHoldsDetected: (wallId) => {
      loadHolds(wallId);
    },
    onScanFailed: () => {
      /* Error notification already handled in useEcho */
    },
  });

  /* Handle new wall uploaded */
  const handleWallCreated = useCallback((newWall) => {
    setWall(newWall);
    setScanStatus('pending_scan');
    setShowUploader(false);
  }, [setWall, setScanStatus]);

  /* Polling fallback: if page reloads with scanning status, poll until complete */
  useEffect(() => {
    if (!wall?.id || !['pending_scan', 'scanning'].includes(scanStatus)) return;

    const interval = setInterval(async () => {
      try {
        const res = await api.walls.get(wall.id);
        setWall(res.data);
        if (res.data.status === 'scan_complete') {
          await loadHolds(wall.id);
          clearInterval(interval);
        } else if (res.data.status === 'scan_failed') {
          clearInterval(interval);
        }
      } catch { /* silently retry */ }
    }, 8000); // Poll every 8s as WebSocket fallback

    return () => clearInterval(interval);
  }, [wall?.id, scanStatus]);

  const isScanning  = ['pending_scan', 'scanning'].includes(scanStatus);
  const hasFailed   = scanStatus === 'scan_failed';
  const hasHolds    = holds.length > 0;

  return (
    <div className="app-layout">

      {/* ── Navbar ────────────────────────────────────────────────────────── */}
      <nav className="navbar">
        <div className="navbar-brand">
          <div className="brand-icon" aria-hidden="true">🧗</div>
          <span>SprayWall</span>
        </div>

        {wall && (
          <div className="navbar-wall-info">
            <span className="navbar-wall-name">{wall.name}</span>
            <WallStatusBadge status={scanStatus} />
          </div>
        )}

        <div className="navbar-actions">
          {wall && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setShowUploader(true)}
              aria-label="Upload a new wall"
            >
              + New Wall
            </button>
          )}
        </div>
      </nav>

      {/* ── Main Content ──────────────────────────────────────────────────── */}
      <main className="wall-detail-main">

        {/* ── Upload Flow ───────────────────────────────────────────────── */}
        {(showUploader || !wall) && (
          <div className="upload-page">
            <div className="upload-hero">
              <h1 className="upload-hero-title">
                <span className="gradient-text">Map Your Wall.</span>
                <br />
                Set Your Routes.
              </h1>
              <p className="upload-hero-sub">
                Upload a photo of your spray wall and AI will detect every hold automatically.
              </p>
            </div>
            <WallUploader onSuccess={handleWallCreated} />
          </div>
        )}

        {/* ── Wall Detail Layout ────────────────────────────────────────── */}
        {wall && !showUploader && (
          <div className="wall-detail-layout">

            {/* ── Hold Map Column ─────────────────────────────────────── */}
            <div className="wall-map-column">

              {/* Scan Status Banner */}
              {isScanning && (
                <div className="scan-banner" role="status" aria-live="polite">
                  <span className="scan-banner-spinner" aria-hidden="true" />
                  <span>
                    Scanning <strong>{wall.name}</strong> for holds…
                    This usually takes 30–90 seconds.
                  </span>
                </div>
              )}

              {hasFailed && (
                <div className="error-banner" role="alert">
                  <span aria-hidden="true">⚠️</span>
                  <span>Scan failed. {wall.scan_error ?? 'Please try re-uploading a clearer photo.'}</span>
                  <button
                    type="button"
                    className="btn btn-sm btn-secondary"
                    onClick={() => setShowUploader(true)}
                  >
                    Re-upload
                  </button>
                </div>
              )}

              {/* Interactive Hold Map */}
              <HoldMapOverlay
                imageUrl={wall.image_url}
                wallName={wall.name}
              />

              {/* Hold interaction hint */}
              {hasHolds && (
                <p className="hold-hint" aria-live="polite">
                  <kbd>Click</kbd> a hold to include/exclude it from route generation.
                  <span className="hold-hint-count">{holds.filter(h => h.excluded).length} excluded</span>
                </p>
              )}
            </div>

            {/* ── Sidebar ──────────────────────────────────────────────── */}
            <RouteGeneratorPanel
              wallId={wall.id}
              onRouteGenerated={() => {}}
            />
          </div>
        )}
      </main>

      {/* ── Global Portals ────────────────────────────────────────────────── */}
      <SaveRouteModal />
      <ToastContainer />
    </div>
  );
}

/* Small status badge for navbar */
function WallStatusBadge({ status }) {
  const map = {
    pending_scan:  { cls: 'badge-muted',   text: 'Queued'   },
    scanning:      { cls: 'badge-orange',  text: 'Scanning' },
    scan_complete: { cls: 'badge-green',   text: 'Ready'    },
    scan_failed:   { cls: 'badge-red',     text: 'Failed'   },
  };
  const { cls, text } = map[status] ?? { cls: 'badge-muted', text: status };
  return <span className={`badge ${cls}`}>{text}</span>;
}
