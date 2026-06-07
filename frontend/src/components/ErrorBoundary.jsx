import { Component } from 'react'

// A failed lazy() chunk import surfaces here. The message varies by browser, so
// match the known shapes for "couldn't fetch/parse a dynamically imported module".
const CHUNK_ERROR_RE =
  /(dynamically imported module|module script failed|ChunkLoadError|Loading chunk|Failed to fetch)/i

function isChunkError(error) {
  if (!error) return false
  return error.name === 'ChunkLoadError' || CHUNK_ERROR_RE.test(error.message || '')
}

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null, isChunk: false }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error, isChunk: isChunkError(error) }
  }

  componentDidCatch(error, info) {
    console.error('Uncaught render error:', error, info)
    // A failed chunk usually means a new deploy swapped the hashed filenames out
    // from under this tab (or a proxy briefly 502'd the asset). Reload once to
    // fetch the current index.html + chunk names. The 10s window guard (shared
    // with main.jsx's vite:preloadError handler) stops an infinite reload loop
    // if the asset is genuinely unrecoverable — then the UI below is shown.
    if (isChunkError(error)) {
      const KEY = 'bs:lastChunkReload'
      const now = Date.now()
      if (now - Number(sessionStorage.getItem(KEY) || 0) > 10000) {
        sessionStorage.setItem(KEY, String(now))
        window.location.reload()
      }
    }
  }

  render() {
    if (this.state.hasError) {
      const { isChunk, error } = this.state
      return (
        <div className="min-h-screen bg-pb-bg flex items-center justify-center p-8">
          <div className="max-w-md text-center">
            <h1 className="font-display text-2xl font-bold text-pb-text mb-3">
              {isChunk ? 'Update available' : 'Something went wrong'}
            </h1>
            <p className="text-pb-faint mb-6 text-sm">
              {isChunk
                ? 'This page failed to load — a new version may have just been deployed. Reload to get the latest.'
                : error?.message || 'An unexpected error occurred.'}
            </p>
            <button
              onClick={() =>
                isChunk
                  ? window.location.reload()
                  : this.setState({ hasError: false, error: null, isChunk: false })
              }
              className="px-4 py-2 rounded font-mono text-sm font-semibold text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              {isChunk ? 'Reload' : 'Try again'}
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
