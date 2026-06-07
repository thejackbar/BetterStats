import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './index.css'
import './styles/theme.css'

// A lazy import() can fail with "Failed to fetch dynamically imported module"
// when a deploy swaps the content-hashed chunk filenames out from under an open
// tab, or when the proxy briefly 502s an asset (see the Jun 2026 admin outage:
// NPM couldn't resolve betterstats-frontend after a recreate). Vite fires
// `vite:preloadError` for exactly this — reload once to pull the current
// index.html + chunk names. The 10s window guard stops an infinite reload loop
// if the asset is genuinely unrecoverable (then the ErrorBoundary UI shows).
window.addEventListener('vite:preloadError', (event) => {
  const KEY = 'bs:lastChunkReload'
  const now = Date.now()
  if (now - Number(sessionStorage.getItem(KEY) || 0) < 10000) return
  sessionStorage.setItem(KEY, String(now))
  event.preventDefault()
  window.location.reload()
})

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
)
