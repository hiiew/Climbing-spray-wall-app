/**
 * WallUploader.jsx — Drag-and-drop wall image upload component
 *
 * Features:
 * - Drag-and-drop + click-to-browse
 * - Image preview with metadata form
 * - XHR upload with real-time progress bar
 * - Accessible: keyboard, ARIA live regions, focus management
 */

import React, { useCallback, useRef, useState } from 'react';
import { api } from '../../api';
import { useWallStore } from '../../hooks/useWallStore';
import './WallUploader.css';

const ACCEPTED_TYPES  = ['image/jpeg', 'image/png', 'image/heic'];
const MAX_SIZE_MB     = 20;
const MAX_SIZE_BYTES  = MAX_SIZE_MB * 1024 * 1024;

function formatBytes(bytes) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function WallUploader({ onSuccess }) {
  const [isDragging,    setIsDragging]    = useState(false);
  const [preview,       setPreview]       = useState(null);
  const [file,          setFile]          = useState(null);
  const [fileError,     setFileError]     = useState(null);
  const [isUploading,   setIsUploading]   = useState(false);
  const [form,          setForm]          = useState({ name: '', angle: 40, width_cm: 244, height_cm: 244 });
  const [formErrors,    setFormErrors]    = useState({});

  const dropRef    = useRef(null);
  const inputRef   = useRef(null);
  const { setUploadProgress, uploadProgress, addNotification, setScanStatus } = useWallStore();

  const validateFile = useCallback((f) => {
    if (!ACCEPTED_TYPES.includes(f.type)) {
      return 'Only JPEG, PNG, and HEIC images are accepted.';
    }
    if (f.size > MAX_SIZE_BYTES) {
      return `File too large (${formatBytes(f.size)}). Maximum is ${MAX_SIZE_MB} MB.`;
    }
    return null;
  }, []);

  const handleFile = useCallback((f) => {
    const err = validateFile(f);
    if (err) { setFileError(err); setPreview(null); setFile(null); return; }

    setFileError(null);
    setFile(f);

    // Generate preview
    const reader = new FileReader();
    reader.onload = (e) => setPreview(e.target.result);
    reader.readAsDataURL(f);

    // Auto-fill name from filename
    if (!form.name) {
      const baseName = f.name.replace(/\.[^/.]+$/, '').replace(/[-_]/g, ' ');
      setForm((prev) => ({ ...prev, name: baseName }));
    }
  }, [form.name, validateFile]);

  const onDrop = useCallback((e) => {
    e.preventDefault();
    setIsDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) handleFile(dropped);
  }, [handleFile]);

  const onDragOver  = (e) => { e.preventDefault(); setIsDragging(true); };
  const onDragLeave = (e) => { if (!dropRef.current.contains(e.relatedTarget)) setIsDragging(false); };

  const validateForm = () => {
    const errs = {};
    if (!form.name.trim())             errs.name      = 'Wall name is required.';
    if (form.angle < 0 || form.angle > 70) errs.angle = 'Angle must be 0–70°.';
    if (!file)                         errs.image     = 'Please select a wall image.';
    setFormErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validateForm() || isUploading) return;

    setIsUploading(true);
    setScanStatus('uploading');

    const formData = new FormData();
    formData.append('image',      file);
    formData.append('name',       form.name);
    formData.append('angle',      String(form.angle));
    formData.append('width_cm',   String(form.width_cm));
    formData.append('height_cm',  String(form.height_cm));

    try {
      const response = await api.walls.create(formData, setUploadProgress);
      setScanStatus('pending_scan');
      addNotification('success', 'Wall uploaded! Scanning for holds…');
      onSuccess?.(response.data);
    } catch (err) {
      setScanStatus('idle');
      setFileError(err.message ?? 'Upload failed. Please try again.');
      addNotification('error', err.message ?? 'Upload failed.');
    } finally {
      setIsUploading(false);
      setUploadProgress(0);
    }
  };

  const clearFile = () => {
    setFile(null);
    setPreview(null);
    setFileError(null);
    if (inputRef.current) inputRef.current.value = '';
  };

  return (
    <div className="wall-uploader" role="region" aria-label="Wall image uploader">
      <form onSubmit={handleSubmit} noValidate>

        {/* ── Drop Zone ─────────────────────────────────────────────────── */}
        {!preview ? (
          <div
            ref={dropRef}
            className={`uploader-dropzone ${isDragging ? 'dragging' : ''} ${fileError ? 'error' : ''}`}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onClick={() => inputRef.current?.click()}
            role="button"
            tabIndex={0}
            aria-label="Drop wall image here or click to browse"
            onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
          >
            <div className="dropzone-icon" aria-hidden="true">🧗</div>
            <p className="dropzone-title">Drop your spray wall photo here</p>
            <p className="dropzone-subtitle">
              or <span className="dropzone-link">click to browse</span>
            </p>
            <p className="dropzone-hint">JPEG, PNG, HEIC · Max {MAX_SIZE_MB} MB · Min 1000×1000px</p>

            {fileError && (
              <p className="dropzone-error" role="alert">{fileError}</p>
            )}

            <input
              ref={inputRef}
              type="file"
              accept="image/jpeg,image/png,image/heic,.heic"
              onChange={(e) => e.target.files[0] && handleFile(e.target.files[0])}
              className="visually-hidden"
              aria-label="Choose wall image file"
              id="wall-image-input"
            />
          </div>
        ) : (
          /* ── Preview ───────────────────────────────────────────────────── */
          <div className="uploader-preview">
            <img src={preview} alt="Wall preview" className="preview-img" />
            <div className="preview-overlay">
              <div className="preview-file-info">
                <span className="preview-filename">{file.name}</span>
                <span className="preview-filesize">{formatBytes(file.size)}</span>
              </div>
              <button
                type="button"
                onClick={clearFile}
                className="btn btn-ghost btn-sm preview-remove"
                aria-label="Remove selected image"
              >
                ✕ Remove
              </button>
            </div>
          </div>
        )}

        {/* ── Metadata Form ──────────────────────────────────────────────── */}
        {preview && (
          <div className="uploader-form" aria-label="Wall metadata">

            <div className="form-group">
              <label className="label" htmlFor="wall-name">Wall Name</label>
              <input
                id="wall-name"
                className={`input ${formErrors.name ? 'input-error' : ''}`}
                type="text"
                placeholder="e.g. Garage Board 40°"
                value={form.name}
                onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                maxLength={100}
                aria-describedby={formErrors.name ? 'wall-name-error' : undefined}
                aria-invalid={!!formErrors.name}
              />
              {formErrors.name && <p id="wall-name-error" className="input-error-msg" role="alert">{formErrors.name}</p>}
            </div>

            <div className="form-row">
              <div className="form-group">
                <label className="label" htmlFor="wall-angle">Angle (°)</label>
                <input
                  id="wall-angle"
                  className="input"
                  type="number"
                  min={0} max={70}
                  value={form.angle}
                  onChange={(e) => setForm((p) => ({ ...p, angle: Number(e.target.value) }))}
                  aria-describedby="angle-hint"
                />
                <p id="angle-hint" className="form-hint">0° = vertical, 70° = severe overhang</p>
              </div>
              <div className="form-group">
                <label className="label" htmlFor="wall-width">Width (cm)</label>
                <input
                  id="wall-width"
                  className="input"
                  type="number"
                  min={50} max={1000}
                  value={form.width_cm}
                  onChange={(e) => setForm((p) => ({ ...p, width_cm: Number(e.target.value) }))}
                />
              </div>
              <div className="form-group">
                <label className="label" htmlFor="wall-height">Height (cm)</label>
                <input
                  id="wall-height"
                  className="input"
                  type="number"
                  min={50} max={1000}
                  value={form.height_cm}
                  onChange={(e) => setForm((p) => ({ ...p, height_cm: Number(e.target.value) }))}
                />
              </div>
            </div>

            {/* ── Upload Progress ──────────────────────────────────────────── */}
            {isUploading && (
              <div className="upload-progress" role="progressbar" aria-valuenow={uploadProgress} aria-valuemin={0} aria-valuemax={100} aria-label="Upload progress">
                <div className="progress-bar">
                  <div className="progress-fill" style={{ width: `${uploadProgress}%` }} />
                </div>
                <span className="progress-label">{uploadProgress}%</span>
              </div>
            )}

            <button
              type="submit"
              className={`btn btn-primary btn-lg uploader-submit ${isUploading ? 'btn-loading' : ''}`}
              disabled={isUploading || !file}
              aria-busy={isUploading}
            >
              {isUploading ? 'Uploading…' : '🔍 Upload & Scan Wall'}
            </button>
          </div>
        )}
      </form>
    </div>
  );
}
