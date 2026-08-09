// Shared client-side form validators for admin uploads + inputs.
// Mirrors the server-side limits so users fail fast (no bandwidth wasted
// on an oversized upload that the server is going to 400 anyway).

// The default limit is for PICKED files headed into ImageEditorModal, which
// crops and re-encodes at <=1600px before anything is uploaded — so the
// original never leaves the browser and can afford to be a straight-off-the-
// camera JPEG (a 24MP DSLR shot runs 8-14 MB). The server-side caps on the
// photo/logo endpoints (8 MB) apply to the editor's OUTPUT, not this file.
export const IMAGE_MAX_BYTES = 15 * 1024 * 1024 // 15 MB — picked-file cap ahead of the crop editor
// For uploads that send the picked file to the server AS-IS (website gallery,
// the shared UploadButton) — matches website.py's _MAX_IMAGE_BYTES.
export const DIRECT_IMAGE_MAX_BYTES = 6 * 1024 * 1024
export const IMAGE_ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']
export const IMAGE_ALLOWED_EXTS = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
export const HEX_COLOR_RE = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i

function fmtBytes(n) {
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  if (n >= 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${n} B`
}

// Returns null if valid, or a user-facing error string.
export function validateImageFile(file, { maxBytes = IMAGE_MAX_BYTES } = {}) {
  if (!file) return 'No file selected'
  const ext = '.' + (file.name || '').split('.').pop().toLowerCase()
  if (!IMAGE_ALLOWED_EXTS.includes(ext)) {
    return `Unsupported file type: ${ext || 'unknown'}. Use JPG, PNG, WEBP or GIF.`
  }
  if (file.type && !IMAGE_ALLOWED_TYPES.includes(file.type)) {
    return `Unsupported MIME type: ${file.type}. Use JPG, PNG, WEBP or GIF.`
  }
  if (file.size > maxBytes) {
    return `File is ${fmtBytes(file.size)} — must be ${fmtBytes(maxBytes)} or smaller.`
  }
  if (file.size === 0) return 'File is empty.'
  return null
}

export function validateHexColor(value) {
  if (!value) return null // empty allowed (treated as unset)
  if (!HEX_COLOR_RE.test(value.trim())) {
    return 'Use a hex colour like #16c784 or #f59e0b.'
  }
  return null
}

// Returns null if valid, or an error string.
// min/max are inclusive. Pass allowEmpty:true to permit an unfilled field.
export function validateIntRange(value, { min, max, allowEmpty = true, label = 'Value' } = {}) {
  if (value === '' || value == null) return allowEmpty ? null : `${label} is required.`
  const n = Number(value)
  if (!Number.isFinite(n) || !Number.isInteger(n)) return `${label} must be a whole number.`
  if (min != null && n < min) return `${label} must be at least ${min}.`
  if (max != null && n > max) return `${label} must be at most ${max}.`
  return null
}
