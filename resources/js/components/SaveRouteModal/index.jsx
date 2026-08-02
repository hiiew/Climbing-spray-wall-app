/**
 * SaveRouteModal/index.jsx
 *
 * Modal dialog for naming, describing, and publishing a generated route.
 * On save, displays the share URL with a copy-to-clipboard button.
 *
 * Accessibility:
 * - Focus trapped inside modal when open
 * - Escape key closes
 * - aria-modal, aria-labelledby, aria-describedby
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api';
import { useWallStore } from '../../hooks/useWallStore';
import './SaveRouteModal.css';

export default function SaveRouteModal() {
  const { isSaveModalOpen, closeSaveModal, currentRoute, setCurrentRoute, addNotification } = useWallStore();

  const [name,        setName]        = useState('');
  const [description, setDescription] = useState('');
  const [isPublic,    setIsPublic]    = useState(true);
  const [isSaving,    setIsSaving]    = useState(false);
  const [shareUrl,    setShareUrl]    = useState(null);
  const [copied,      setCopied]      = useState(false);
  const [nameError,   setNameError]   = useState('');

  const nameInputRef = useRef(null);
  const closeRef     = useRef(null);

  /* Focus management */
  useEffect(() => {
    if (isSaveModalOpen) {
      setShareUrl(null);
      setCopied(false);
      setName(currentRoute?.name ?? '');
      setDescription(currentRoute?.description ?? '');
      setTimeout(() => nameInputRef.current?.focus(), 50);
    }
  }, [isSaveModalOpen, currentRoute]);

  /* Escape key */
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape' && isSaveModalOpen) closeSaveModal(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isSaveModalOpen, closeSaveModal]);

  /* Focus trap */
  const trapFocus = useCallback((e) => {
    const modal     = e.currentTarget;
    const focusable = modal.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const first = focusable[0];
    const last  = focusable[focusable.length - 1];

    if (e.key === 'Tab') {
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last.focus(); }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    }
  }, []);

  const handleSave = async () => {
    if (!name.trim()) { setNameError('Route name is required.'); nameInputRef.current?.focus(); return; }
    setNameError('');
    setIsSaving(true);

    try {
      const response = await api.routes.save(currentRoute.id, {
        name:         name.trim(),
        description:  description.trim() || null,
        is_published: isPublic,
      });

      setCurrentRoute(response.data);
      if (response.data.share_url) setShareUrl(response.data.share_url);
      addNotification('success', `Route "${name}" saved!`);
    } catch (err) {
      addNotification('error', err.message ?? 'Failed to save route.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleCopy = async () => {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      // Fallback for older browsers
      const input = document.createElement('input');
      input.value = shareUrl;
      document.body.appendChild(input);
      input.select();
      document.execCommand('copy');
      document.body.removeChild(input);
      setCopied(true);
    }
  };

  if (!isSaveModalOpen) return null;

  return (
    /* Backdrop */
    <div
      className="modal-backdrop"
      onClick={(e) => { if (e.target === e.currentTarget) closeSaveModal(); }}
      aria-hidden="true"
    >
      {/* Dialog */}
      <div
        className="modal-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="save-modal-title"
        aria-describedby="save-modal-desc"
        onKeyDown={trapFocus}
      >
        {/* Header */}
        <div className="modal-header">
          <h2 id="save-modal-title" className="modal-title">
            💾 Save Route
          </h2>
          <button
            ref={closeRef}
            type="button"
            className="btn btn-ghost btn-icon modal-close"
            onClick={closeSaveModal}
            aria-label="Close save route dialog"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="modal-body">
          {!shareUrl ? (
            <>
              <p id="save-modal-desc" className="modal-desc">
                Give your route a name to save it. Publish it to generate a shareable link.
              </p>

              {/* Route badges */}
              {currentRoute && (
                <div className="modal-route-meta">
                  <span className="badge badge-orange">{currentRoute.grade}</span>
                  <span className="badge badge-blue">{currentRoute.style}</span>
                  <span className="badge badge-muted">{currentRoute.hold_count} holds</span>
                </div>
              )}

              {/* Name */}
              <div className="form-group">
                <label className="label" htmlFor="route-name">Route Name *</label>
                <input
                  ref={nameInputRef}
                  id="route-name"
                  className={`input ${nameError ? 'input-error' : ''}`}
                  type="text"
                  placeholder="e.g. Tuesday Crusher"
                  value={name}
                  onChange={(e) => { setName(e.target.value); setNameError(''); }}
                  maxLength={100}
                  aria-describedby={nameError ? 'route-name-error' : undefined}
                  aria-invalid={!!nameError}
                  aria-required="true"
                />
                {nameError && (
                  <p id="route-name-error" className="input-error-msg" role="alert">{nameError}</p>
                )}
              </div>

              {/* Description */}
              <div className="form-group">
                <label className="label" htmlFor="route-desc">Description</label>
                <textarea
                  id="route-desc"
                  className="input textarea"
                  placeholder="Describe the movement, crux, or beta…"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  maxLength={1000}
                  rows={3}
                />
              </div>

              {/* Publish toggle */}
              <label className="publish-toggle" htmlFor="is-public">
                <input
                  id="is-public"
                  type="checkbox"
                  className="toggle-checkbox"
                  checked={isPublic}
                  onChange={(e) => setIsPublic(e.target.checked)}
                />
                <div className="toggle-track" aria-hidden="true">
                  <div className="toggle-thumb" />
                </div>
                <div className="toggle-label">
                  <span className="toggle-title">Make public</span>
                  <span className="toggle-hint">Generate a shareable link</span>
                </div>
              </label>
            </>
          ) : (
            /* Share URL view */
            <div className="share-view" aria-live="polite">
              <div className="share-success-icon" aria-hidden="true">🎉</div>
              <h3 className="share-success-title">Route Saved!</h3>
              <p className="share-success-desc">
                Share <strong>{name}</strong> with anyone using this link:
              </p>

              <div className="share-url-row">
                <input
                  className="input share-url-input"
                  type="text"
                  value={shareUrl}
                  readOnly
                  aria-label="Share URL"
                  onClick={(e) => e.target.select()}
                />
                <button
                  type="button"
                  className={`btn ${copied ? 'btn-secondary' : 'btn-primary'} share-copy-btn`}
                  onClick={handleCopy}
                  aria-label={copied ? 'Link copied!' : 'Copy share link'}
                >
                  {copied ? '✓ Copied' : '📋 Copy'}
                </button>
              </div>

              {copied && (
                <p className="copy-confirm" role="status" aria-live="polite">
                  Link copied to clipboard!
                </p>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        {!shareUrl && (
          <div className="modal-footer">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={closeSaveModal}
            >
              Cancel
            </button>
            <button
              type="button"
              className={`btn btn-primary ${isSaving ? 'btn-loading' : ''}`}
              onClick={handleSave}
              disabled={isSaving}
              aria-busy={isSaving}
            >
              {isSaving ? 'Saving…' : '💾 Save Route'}
            </button>
          </div>
        )}

        {shareUrl && (
          <div className="modal-footer">
            <button type="button" className="btn btn-primary" onClick={closeSaveModal}>
              Done
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
