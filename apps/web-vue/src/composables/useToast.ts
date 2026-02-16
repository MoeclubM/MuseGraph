import { reactive } from 'vue'
import type { ToastMessage, ToastType } from '@/types'

const toasts = reactive<ToastMessage[]>([])
let nextId = 0

function addToast(message: string, type: ToastType = 'info', duration = 4000) {
  const id = nextId++
  toasts.push({ id, message, type })
  if (duration > 0) {
    setTimeout(() => removeToast(id), duration)
  }
}

function removeToast(id: number) {
  const index = toasts.findIndex((t) => t.id === id)
  if (index !== -1) {
    toasts.splice(index, 1)
  }
}

export function useToast() {
  return {
    toasts,
    addToast,
    removeToast,
    success: (message: string, duration?: number) => addToast(message, 'success', duration),
    error: (message: string, duration?: number) => addToast(message, 'error', duration),
    warning: (message: string, duration?: number) => addToast(message, 'warning', duration),
    info: (message: string, duration?: number) => addToast(message, 'info', duration),
  }
}
