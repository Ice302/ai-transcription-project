import { CircleCheck, Info, TriangleAlert, X } from 'lucide-react'
import { useCallback, useRef, useState } from 'react'
import { ToastContext } from '../hooks/toast'

const ICONS = { success: CircleCheck, error: TriangleAlert, info: Info }

// Black pill toasts, bottom centre; announced to screen readers.
export default function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const next = useRef(0)

  const dismiss = useCallback((id) => setToasts((list) => list.filter((t) => t.id !== id)), [])
  const push = useCallback(
    (message, { tone = 'info', action, timeout = 4500 } = {}) => {
      const id = ++next.current
      setToasts((list) => [...list.slice(-3), { id, message, tone, action }])
      if (timeout) setTimeout(() => dismiss(id), timeout)
    },
    [dismiss],
  )

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div aria-live="polite" className="no-print pointer-events-none fixed inset-x-0 bottom-5 z-50 flex flex-col items-center gap-2 px-4">
        {toasts.map((t) => {
          const Icon = ICONS[t.tone] || Info
          return (
            <div
              key={t.id}
              className="animate-rise pointer-events-auto flex max-w-xl items-center gap-3 rounded-full bg-ink py-2 pl-3 pr-2 text-sm text-on-ink shadow-2xl"
            >
              <Icon className={`size-4 shrink-0 ${t.tone === 'error' ? 'text-signal' : 'text-lime'}`} />
              <span className="min-w-0 flex-1 truncate">{t.message}</span>
              {t.action && (
                <button
                  type="button"
                  onClick={() => {
                    t.action.onClick()
                    dismiss(t.id)
                  }}
                  className="rounded-full bg-lime px-3 py-1 text-xs font-semibold text-[#131312]"
                >
                  {t.action.label}
                </button>
              )}
              <button type="button" aria-label="Dismiss" onClick={() => dismiss(t.id)} className="rounded-full p-1 opacity-60 hover:opacity-100">
                <X className="size-3.5" />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}
