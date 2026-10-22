import { createContext, useContext } from 'react'

export const ToastContext = createContext(() => {})

// push(message, { tone: 'info' | 'success' | 'error', action: { label, onClick }, timeout })
export const useToast = () => useContext(ToastContext)
