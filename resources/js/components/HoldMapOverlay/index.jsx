/**
 * HoldMapOverlay/index.jsx
 *
 * Renders an SVG overlay on top of the wall image.
 * Each detected hold is drawn as an ellipse matching its bounding box,
 * with colour determined by: excluded → default → route role.
 *
 * Coordinate system: all hold x/y/width/height values are normalised [0–1].
 * The SVG uses viewBox="0 0 1 1" and preserveAspectRatio="none" so it
 * stretches to exactly cover the underlying image at any resolution.
 *
 * Features:
 * - Click to toggle hold exclusion
 * - Hover tooltip with hold metadata
 * - Animated hold-pop entrance
 * - Scan scanning overlay with animated sweep line
 * - Keyboard navigable (Tab + Enter/Space)
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useWallStore, ROLE_COLORS } from '../../hooks/useWallStore';
import './HoldMapOverlay.css';

/* Scan status that show the scanning animation */
const SCANNING_STATUSES = ['pending_scan', 'scanning'];

/* Minimum rendered size for a hold marker (prevents invisible holds) */
const MIN_HOLD_SIZE = 0.012;

export default function HoldMapOverlay({ imageUrl, wallName = 'Wall' }) {
  const {
    holds, scanStatus, excludedHolds, routeHoldMap, currentRoute,
    toggleHoldExclusion, setSelectedHold, getHoldDisplayProps,
  } = useWallStore();

  const [hoveredHold, setHoveredHold] = useState(null);
  const [tooltip,     setTooltip]     = useState({ x: 0, y: 0, visible: false });
  const containerRef  = useRef(null);
  const svgRef        = useRef(null);

  const isScanning    = SCANNING_STATUSES.includes(scanStatus);
  const hasHolds      = holds.length > 0;

  /* ── Tooltip position from SVG normalised coords → container px ──────── */
  const getTooltipPos = useCallback((hold) => {
    if (!containerRef.current) return { x: 0, y: 0 };
    const rect = containerRef.current.getBoundingClientRect();
    return {
      x: (hold.center_x) * rect.width,
      y: (hold.center_y - hold.height / 2) * rect.height - 12,
    };
  }, []);

  const handleHoldClick = useCallback((e, hold) => {
    e.stopPropagation();
    toggleHoldExclusion(hold.id);
  }, [toggleHoldExclusion]);

  const handleHoldKeyDown = useCallback((e, hold) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      toggleHoldExclusion(hold.id);
    }
    if (e.key === 'i') {
      setSelectedHold(hold);
    }
  }, [toggleHoldExclusion, setSelectedHold]);

  const handleHoldHover = useCallback((hold) => {
    setHoveredHold(hold);
    setTooltip({ ...getTooltipPos(hold), visible: true });
  }, [getTooltipPos]);

  const handleHoldLeave = useCallback(() => {
    setHoveredHold(null);
    setTooltip((t) => ({ ...t, visible: false }));
  }, []);

  /* ── Render each hold as SVG ellipse ─────────────────────────────────── */
  const renderHold = (hold, idx) => {
    const props      = getHoldDisplayProps(hold.id);
    const isExcluded = props.isExcluded;
    const isInRoute  = props.isInRoute;
    const isHovered  = hoveredHold?.id === hold.id;

    /* Centre + radii in SVG coordinate space [0–1] */
    const cx = hold.center_x;
    const cy = hold.center_y;
    const rx = Math.max(MIN_HOLD_SIZE, hold.width  / 2) * 1.1;
    const ry = Math.max(MIN_HOLD_SIZE, hold.height / 2) * 1.1;

    const glowId    = `glow-${hold.id}`;
    const gradId    = `grad-${hold.id}`;
    const roleLabel = isInRoute ? ROLE_COLORS[props.role]?.label : null;

    return (
      <g
        key={hold.id}
        className={[
          'hold-group',
          isExcluded  ? 'hold-excluded'  : '',
          isInRoute   ? `hold-role-${props.role}` : '',
          isHovered   ? 'hold-hovered'   : '',
        ].join(' ')}
        role="button"
        tabIndex={0}
        aria-label={[
          `Hold ${idx + 1}`,
          hold.type !== 'unknown' ? hold.type : '',
          hold.color !== 'unknown' ? hold.color : '',
          isExcluded ? '(excluded)' : '',
          roleLabel ? `(${roleLabel})` : '',
        ].filter(Boolean).join(' ')}
        aria-pressed={!isExcluded}
        onClick={(e) => handleHoldClick(e, hold)}
        onMouseEnter={() => handleHoldHover(hold)}
        onMouseLeave={handleHoldLeave}
        onKeyDown={(e) => handleHoldKeyDown(e, hold)}
        style={{ animationDelay: `${idx * 18}ms` }}
      >
        <defs>
          {/* Soft glow filter */}
          <filter id={glowId} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="0.004" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Radial gradient fill */}
          <radialGradient id={gradId} cx="35%" cy="30%" r="65%">
            <stop offset="0%"   stopColor={props.fill}   stopOpacity="0.9" />
            <stop offset="100%" stopColor={props.stroke}  stopOpacity="0.6" />
          </radialGradient>
        </defs>

        {/* Hold body */}
        <ellipse
          cx={cx} cy={cy} rx={rx} ry={ry}
          fill={`url(#${gradId})`}
          stroke={props.stroke}
          strokeWidth={isInRoute ? 0.003 : 0.002}
          filter={isHovered || isInRoute ? `url(#${glowId})` : undefined}
          className="hold-ellipse"
        />

        {/* Route role label (only on larger holds) */}
        {isInRoute && rx > 0.025 && (
          <text
            x={cx} y={cy}
            textAnchor="middle"
            dominantBaseline="central"
            className="hold-role-text"
            fontSize="0.022"
            fill="white"
            fontWeight="700"
          >
            {roleLabel?.[0]}
          </text>
        )}

        {/* Position number in route */}
        {isInRoute && (
          <text
            x={cx + rx * 0.7} y={cy - ry * 0.7}
            textAnchor="middle"
            dominantBaseline="central"
            className="hold-order-text"
            fontSize="0.015"
            fill={props.fill}
            fontWeight="800"
          >
            {routeHoldMap[hold.id]?.position_order}
          </text>
        )}

        {/* Excluded X mark */}
        {isExcluded && (
          <text
            x={cx} y={cy}
            textAnchor="middle"
            dominantBaseline="central"
            fontSize="0.022"
            fill="rgba(255,255,255,0.3)"
          >
            ✕
          </text>
        )}
      </g>
    );
  };

  return (
    <div className="hold-map-container" ref={containerRef} aria-label="Interactive hold map">

      {/* ── Wall Image ───────────────────────────────────────────────────── */}
      <img
        src={imageUrl}
        alt={`${wallName} spray wall`}
        className="hold-map-image"
        draggable={false}
      />

      {/* ── SVG Hold Overlay ─────────────────────────────────────────────── */}
      {hasHolds && (
        <svg
          ref={svgRef}
          className="hold-map-svg"
          viewBox="0 0 1 1"
          preserveAspectRatio="none"
          aria-label={`${holds.length} holds detected`}
          role="group"
        >
          {holds.map((hold, idx) => renderHold(hold, idx))}
        </svg>
      )}

      {/* ── Scanning Overlay ─────────────────────────────────────────────── */}
      {isScanning && (
        <div className="scanning-overlay" aria-live="polite" aria-label="Scanning wall for holds">
          <div className="scan-line" aria-hidden="true" />
          <div className="scanning-badge">
            <span className="scanning-spinner" aria-hidden="true" />
            <span>Scanning for holds…</span>
          </div>
        </div>
      )}

      {/* ── Empty State ───────────────────────────────────────────────────── */}
      {scanStatus === 'scan_failed' && (
        <div className="scan-failed-overlay">
          <span className="scan-failed-icon" aria-hidden="true">⚠️</span>
          <p>Scan failed. Please try re-uploading a clearer photo.</p>
        </div>
      )}

      {/* ── Hold Tooltip ─────────────────────────────────────────────────── */}
      {hoveredHold && tooltip.visible && (
        <div
          className="hold-tooltip"
          style={{ left: tooltip.x, top: tooltip.y }}
          role="tooltip"
          id="hold-tooltip"
          aria-hidden="true"
        >
          <span className="tooltip-type">{hoveredHold.type}</span>
          <span
            className="tooltip-color-dot"
            style={{ background: hoveredHold.color_hex }}
            aria-hidden="true"
          />
          <span className="tooltip-color">{hoveredHold.color}</span>
          {hoveredHold.is_verified === false && (
            <span className="tooltip-unverified">⚠ Unverified</span>
          )}
          <span className="tooltip-hint">Click to exclude/include</span>
        </div>
      )}

      {/* ── Legend ───────────────────────────────────────────────────────── */}
      {currentRoute && (
        <div className="hold-map-legend" aria-label="Route hold roles legend">
          {Object.entries(ROLE_COLORS).map(([role, { fill, label }]) => (
            <div key={role} className="legend-item">
              <span className="legend-dot" style={{ background: fill }} aria-hidden="true" />
              <span>{label}</span>
            </div>
          ))}
        </div>
      )}

      {/* ── Hold count badge ─────────────────────────────────────────────── */}
      {hasHolds && (
        <div className="hold-count-badge" aria-label={`${holds.length} holds detected`}>
          {holds.length} holds
        </div>
      )}
    </div>
  );
}
