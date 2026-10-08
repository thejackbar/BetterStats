import { createContext, useCallback, useContext, useState } from 'react'

const ToastContext = createContext(null)

let _nextId = 0

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const dismiss = useCallback((id) => {
    setToasts(t => t.filter(x => x.id !== id))
  }, [])

  const add = useCallback((message, type = 'info', duration = 4000) => {
    const id = ++_nextId
    setToasts(t => [...t, { id, message, type }])
    setTimeout(() => dismiss(id), duration)
  }, [dismiss])

  const toast = {
    success: (msg) => add(msg, 'success'),
    error:   (msg) => add(msg, 'error', 6000),
    info:    (msg) => add(msg, 'info'),
  }

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <ToastContainer toasts={toasts} dismiss={dismiss} />
    </ToastContext.Provider>
  )
}

export function useToast() {
  return useContext(ToastContext)
}

const STYLES = {
  success: 'bg-green-900/90 border-green-600/40 text-green-100',
  error:   'bg-red-900/90 border-red-600/40 text-red-100',
  info:    'bg-pb-surface2 border-pb-hairline text-pb-text',
}

const ICONS = {
  success: '✓',
  error:   '✕',
  info:    'ℹ',
}

function ToastContainer({ toasts, dismiss }) {
  if (!toasts.length) return null
  return (
    // `--pb-bottom-bar` is set by a screen that pins a bar to the bottom of a
    // phone (the Selection board's Confirm bar), so a toast sits above it
    // instead of covering the button it is reporting on. Unset it is 0px.
    <div className="fixed right-4 z-[9999] flex flex-col gap-2 pointer-events-none"
      style={{ bottom: 'calc(1rem + var(--pb-bottom-bar, 0px))' }}>
      {toasts.map(t => (
        <div
          key={t.id}
          className={`flex items-start gap-2.5 px-4 py-3 rounded-lg border shadow-lg text-sm max-w-sm pointer-events-auto ${STYLES[t.type]}`}
        >
          <span className="font-bold shrink-0 mt-px">{ICONS[t.type]}</span>
          <span className="flex-1">{t.message}</span>
          <button
            onClick={() => dismiss(t.id)}
            className="shrink-0 opacity-60 hover:opacity-100 leading-none ml-1"
            aria-label="Dismiss"
          >×</button>
        </div>
      ))}
    </div>
  )
}
