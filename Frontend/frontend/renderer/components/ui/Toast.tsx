import { useState, useCallback, useRef } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { X, CheckCircle2, XCircle, AlertTriangle, Info } from 'lucide-react'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface Toast {
  id: number
  message: string
  type: ToastType
}

const ICONS: Record<ToastType, React.ReactNode> = {
  success: <CheckCircle2 size={16} />,
  error:   <XCircle size={16} />,
  warning: <AlertTriangle size={16} />,
  info:    <Info size={16} />,
}

const STYLES: Record<ToastType, string> = {
  success: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300',
  error:   'border-red-500/40 bg-red-500/10 text-red-300',
  warning: 'border-yellow-500/40 bg-yellow-500/10 text-yellow-300',
  info:    'border-blue-500/40 bg-blue-500/10 text-blue-300',
}

export function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([])
  const counter = useRef(0)

  const showToast = useCallback((message: string, type: ToastType = 'info', duration = 4000) => {
    const id = ++counter.current
    setToasts(prev => [...prev, { id, message, type }])
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), duration)
  }, [])

  const dismissToast = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  return { toasts, showToast, dismissToast }
}

interface ToastContainerProps {
  toasts: Toast[]
  onDismiss: (id: number) => void
}

export function ToastContainer({ toasts, onDismiss }: ToastContainerProps) {
  return (
    <div className="fixed top-4 right-4 z-[200] flex flex-col gap-2 pointer-events-none">
      <AnimatePresence>
        {toasts.map(toast => (
          <motion.div
            key={toast.id}
            initial={{ opacity: 0, x: 40, scale: 0.95 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 40, scale: 0.95 }}
            transition={{ duration: 0.18 }}
            className={`pointer-events-auto flex items-start gap-2.5 px-3.5 py-2.5 rounded-xl border text-xs font-medium shadow-xl max-w-xs backdrop-blur-sm ${STYLES[toast.type]}`}
          >
            <span className="mt-0.5 shrink-0">{ICONS[toast.type]}</span>
            <span className="leading-relaxed flex-1">{toast.message}</span>
            <button
              onClick={() => onDismiss(toast.id)}
              className="shrink-0 mt-0.5 opacity-60 hover:opacity-100 transition-opacity"
            >
              <X size={13} />
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}
