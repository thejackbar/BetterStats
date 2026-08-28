/**
 * How long a video runs, as the admin types it and as a reader sees it.
 *
 * Stored in seconds so the display format is decided once, rather than each
 * admin typing their own ("2m 45s" / "2:45" / "2 min"). The input accepts all
 * of those and the page renders one of them.
 */

/** "2m 45s" from 165. Mirrors format_duration in the backend service. */
export function formatDuration(seconds) {
  const n = Number(seconds)
  if (!Number.isFinite(n) || n < 1) return null
  const hours = Math.floor(n / 3600)
  const minutes = Math.floor((n % 3600) / 60)
  const secs = Math.floor(n % 60)
  if (hours) {
    if (!minutes && !secs) return `${hours}h`
    // The 0m is kept when there are seconds but no minutes, or "2h 45s" reads
    // as though the 45 might be minutes.
    return secs ? `${hours}h ${minutes}m ${secs}s` : `${hours}h ${minutes}m`
  }
  if (minutes) return secs ? `${minutes}m ${secs}s` : `${minutes}m`
  return `${secs}s`
}

/**
 * Seconds from whatever the admin typed. Accepts "2:45", "1:02:45",
 * "2m 45s", "2 min 45 sec" and a bare "165", because the field is filled in
 * by hand often enough that refusing a reasonable spelling is just friction.
 * Anything unreadable returns null rather than a wrong number.
 */
export function parseDuration(text) {
  const raw = String(text ?? '').trim().toLowerCase()
  if (!raw) return null

  // Clock form: mm:ss or hh:mm:ss
  if (/^\d+(:\d{1,2}){1,2}$/.test(raw)) {
    const parts = raw.split(':').map(Number)
    const secs = parts.length === 3
      ? parts[0] * 3600 + parts[1] * 60 + parts[2]
      : parts[0] * 60 + parts[1]
    return secs > 0 ? secs : null
  }

  // Unit form: 1h 2m 45s, 2 min 45 sec, 2m45s.
  // The unit is closed with a negative lookahead rather than \b, because \b
  // does not fire between the m and the 4 of "2m45s" — both are word
  // characters — so the no-space form silently read as 45 seconds.
  const units = [...raw.matchAll(/(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours|m|min|mins|minute|minutes|s|sec|secs|second|seconds)(?![a-z])/g)]
  if (units.length) {
    let total = 0
    for (const [, value, unit] of units) {
      const n = parseFloat(value)
      if (unit.startsWith('h')) total += n * 3600
      else if (unit.startsWith('m')) total += n * 60
      else total += n
    }
    return total > 0 ? Math.round(total) : null
  }

  // A bare number is seconds.
  if (/^\d+(\.\d+)?$/.test(raw)) {
    const n = Math.round(parseFloat(raw))
    return n > 0 ? n : null
  }
  return null
}

/**
 * Read the runtime out of an uploaded file, in the browser, so the field fills
 * itself in. Same approach the poster capture takes, and best-effort for the
 * same reason: a codec the browser cannot decode resolves to null and the
 * admin types it instead.
 */
export function readDuration(file, { timeoutMs = 8000 } = {}) {
  return new Promise((resolve) => {
    let settled = false
    const url = URL.createObjectURL(file)
    const video = document.createElement('video')
    const done = (value) => {
      if (settled) return
      settled = true
      URL.revokeObjectURL(url)
      video.removeAttribute('src')
      resolve(value)
    }
    const timer = setTimeout(() => done(null), timeoutMs)
    video.preload = 'metadata'
    video.muted = true
    video.onerror = () => { clearTimeout(timer); done(null) }
    video.onloadedmetadata = () => {
      clearTimeout(timer)
      const d = video.duration
      done(Number.isFinite(d) && d >= 1 ? Math.round(d) : null)
    }
    video.src = url
  })
}
