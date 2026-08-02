/**
 * RouteGeneratorPanel/index.jsx
 *
 * Sidebar panel for generating AI routes. Controls:
 * - Grade (V0–V16 slider + label)
 * - Style (icon-button pill selector)
 * - Body type (compact selector)
 * - Hold count (auto or manual slider)
 *
 * Shows the current route's quality score and hold breakdown when a route exists.
 */

import React, { useState } from 'react';
import { api } from '../../api';
import { useWallStore, ROLE_COLORS } from '../../hooks/useWallStore';
import './RouteGeneratorPanel.css';

const GRADES = ['V0','V1','V2','V3','V4','V5','V6','V7','V8','V9','V10','V11','V12','V13','V14','V15','V16'];

const STYLES = [
  { key: 'dynamic',      icon: '⚡', label: 'Dynamic',      desc: 'Big, powerful moves' },
  { key: 'balance',      icon: '🧘', label: 'Balance',       desc: 'Precise footwork' },
  { key: 'compression',  icon: '🤜', label: 'Compression',   desc: 'Body tension' },
  { key: 'endurance',    icon: '🔁', label: 'Endurance',     desc: 'Sustained effort' },
  { key: 'coordination', icon: '🎯', label: 'Coordination',  desc: 'Timing & sequence' },
];

const BODY_TYPES = [
  { key: 'default', label: 'Default' },
  { key: 'tall',    label: 'Tall'    },
  { key: 'short',   label: 'Short'   },
];

function GradeLabel({ grade }) {
  const idx = GRADES.indexOf(grade);
  const pct = idx / (GRADES.length - 1);
  const color = `hsl(${140 - pct * 140}, 80%, 55%)`;
  return (
    <span className="grade-label" style={{ color }} aria-label={`Grade ${grade}`}>
      {grade}
    </span>
  );
}

function QualityBar({ score }) {
  const pct   = Math.round(score * 100);
  const color = score > 0.8 ? 'var(--accent-green)' : score > 0.6 ? 'var(--accent-orange)' : 'var(--accent-red)';
  return (
    <div className="quality-bar-wrap" aria-label={`Quality score ${pct}%`}>
      <div className="quality-bar">
        <div className="quality-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="quality-pct" style={{ color }}>{pct}%</span>
    </div>
  );
}

export default function RouteGeneratorPanel({ wallId, onRouteGenerated }) {
  const [grade,     setGrade]     = useState('V5');
  const [style,     setStyle]     = useState('dynamic');
  const [bodyType,  setBodyType]  = useState('default');
  const [holdCount, setHoldCount] = useState('auto');
  const [manualCount, setManualCount] = useState(8);

  const { isGenerating, setGenerating, setCurrentRoute, currentRoute,
          addNotification, clearRoute, openSaveModal, excludedHolds, holds } = useWallStore();

  const activeHolds  = holds.filter((h) => !excludedHolds.has(h.id)).length;
  const canGenerate  = activeHolds >= 4 && !isGenerating;

  const handleGenerate = async () => {
    if (!canGenerate) return;
    setGenerating(true);

    try {
      const response = await api.routes.generate(wallId, {
        grade,
        style,
        body_type:  bodyType,
        hold_count: holdCount === 'auto' ? 'auto' : manualCount,
      });

      setCurrentRoute(response.data);
      addNotification('success', `Route generated! Grade ${response.data.grade} · ${response.data.hold_count} holds`);
      onRouteGenerated?.(response.data);
    } catch (err) {
      addNotification('error', err.message ?? 'Route generation failed.');
    } finally {
      setGenerating(false);
    }
  };

  return (
    <aside className="route-panel glass" aria-label="Route generator">

      {/* ── Header ────────────────────────────────────────────────────────── */}
      <div className="route-panel-header">
        <h2 className="route-panel-title">
          <span aria-hidden="true">🧗</span> Generate Route
        </h2>
        {activeHolds < 4 && (
          <p className="route-panel-warning" role="alert">
            ⚠ Need ≥ 4 active holds ({activeHolds} available)
          </p>
        )}
      </div>

      <hr className="divider" />

      {/* ── Grade Slider ──────────────────────────────────────────────────── */}
      <div className="panel-section">
        <div className="panel-section-header">
          <label className="label" htmlFor="grade-slider">Difficulty</label>
          <GradeLabel grade={grade} />
        </div>
        <input
          id="grade-slider"
          type="range"
          className="grade-slider"
          min={0}
          max={GRADES.length - 1}
          value={GRADES.indexOf(grade)}
          onChange={(e) => setGrade(GRADES[Number(e.target.value)])}
          aria-valuetext={grade}
          aria-label="Route difficulty grade"
        />
        <div className="grade-endpoints" aria-hidden="true">
          <span>V0 · Beginner</span>
          <span>V16 · Elite</span>
        </div>
      </div>

      {/* ── Style Selector ────────────────────────────────────────────────── */}
      <div className="panel-section">
        <p className="label">Style</p>
        <div className="style-grid" role="radiogroup" aria-label="Route style">
          {STYLES.map((s) => (
            <button
              key={s.key}
              type="button"
              role="radio"
              aria-checked={style === s.key}
              className={`style-btn ${style === s.key ? 'active' : ''}`}
              onClick={() => setStyle(s.key)}
              title={s.desc}
            >
              <span className="style-icon" aria-hidden="true">{s.icon}</span>
              <span className="style-label">{s.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* ── Body Type ────────────────────────────────────────────────────── */}
      <div className="panel-section">
        <p className="label">Body Type</p>
        <div className="body-type-row" role="radiogroup" aria-label="Body type">
          {BODY_TYPES.map((b) => (
            <button
              key={b.key}
              type="button"
              role="radio"
              aria-checked={bodyType === b.key}
              className={`body-type-btn ${bodyType === b.key ? 'active' : ''}`}
              onClick={() => setBodyType(b.key)}
            >
              {b.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Hold Count ───────────────────────────────────────────────────── */}
      <div className="panel-section">
        <div className="panel-section-header">
          <p className="label">Hold Count</p>
          <button
            type="button"
            className={`auto-toggle ${holdCount === 'auto' ? 'active' : ''}`}
            onClick={() => setHoldCount(holdCount === 'auto' ? 'manual' : 'auto')}
            aria-pressed={holdCount === 'auto'}
          >
            Auto
          </button>
        </div>

        {holdCount === 'manual' && (
          <div className="count-slider-row">
            <input
              type="range"
              className="grade-slider"
              min={4} max={20}
              value={manualCount}
              onChange={(e) => setManualCount(Number(e.target.value))}
              aria-label="Number of holds in route"
              aria-valuetext={`${manualCount} holds`}
            />
            <span className="count-value" aria-live="polite">{manualCount}</span>
          </div>
        )}
        {holdCount === 'auto' && (
          <p className="auto-hint">Hold count determined by difficulty grade</p>
        )}
      </div>

      {/* ── Active Holds Counter ─────────────────────────────────────────── */}
      <div className="active-holds-row">
        <span className="active-holds-label">Active holds</span>
        <span className="active-holds-count">{activeHolds} / {holds.length}</span>
      </div>

      {/* ── Generate Button ──────────────────────────────────────────────── */}
      <button
        type="button"
        className={`btn btn-primary btn-lg generate-btn ${isGenerating ? 'btn-loading' : ''}`}
        onClick={handleGenerate}
        disabled={!canGenerate}
        aria-busy={isGenerating}
        aria-label={isGenerating ? 'Generating route…' : `Generate ${grade} ${style} route`}
      >
        {isGenerating ? 'Generating…' : '✨ Generate Route'}
      </button>

      {/* ── Current Route Summary ────────────────────────────────────────── */}
      {currentRoute && (
        <div className="current-route-summary" aria-label="Current route details" aria-live="polite">
          <hr className="divider" />

          <div className="route-summary-header">
            <div>
              <span className="badge badge-orange">{currentRoute.grade}</span>
              <span className="badge badge-blue" style={{ marginLeft: 6 }}>{currentRoute.style}</span>
            </div>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={clearRoute}
              aria-label="Clear current route"
            >
              Clear
            </button>
          </div>

          <div className="route-summary-stats">
            <div className="stat-item">
              <span className="stat-value">{currentRoute.hold_count}</span>
              <span className="stat-label">Holds</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Quality</span>
              <QualityBar score={currentRoute.quality_score ?? 0} />
            </div>
          </div>

          {/* Role breakdown */}
          <div className="role-breakdown" aria-label="Hold roles in route">
            {Object.entries(ROLE_COLORS).map(([role, { fill, label }]) => {
              const count = currentRoute.holds?.filter((h) => h.role === role).length ?? 0;
              if (!count) return null;
              return (
                <div key={role} className="role-chip" style={{ '--role-color': fill }}>
                  <span className="role-dot" aria-hidden="true" />
                  <span>{count} {label}</span>
                </div>
              );
            })}
          </div>

          <div className="route-action-row">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleGenerate}
              disabled={!canGenerate}
              aria-label="Regenerate a new route"
            >
              🔄 Regenerate
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={openSaveModal}
              aria-label="Save this route"
            >
              💾 Save Route
            </button>
          </div>
        </div>
      )}
    </aside>
  );
}
