// Shared client-side form validators for admin uploads + inputs.
// Mirrors the server-side limits so users fail fast (no bandwidth wasted
// on a 5 MB upload that the server is going to 400 anyway).

export const IMAGE_MAX_BYTES = 2 * 1024 * 1024 // 2 MB — matches LOGO_MAX_BYTES / PHOTO_MAX_BYTES
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
