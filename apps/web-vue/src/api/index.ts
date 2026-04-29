import axios from 'axios'
import router from '@/router'
import { useToast } from '@/composables/useToast'

function sanitizeErrorMessage(value: unknown, fallback: string): string {
  const raw = String(value || '').trim()
  if (!raw) return fallback
  const lowered = raw.toLowerCase()
  if (!lowered.includes('<html') && !lowered.includes('<!doctype html') && !lowered.includes('<body')) {
    return raw
  }
  const cleaned = raw.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
  return cleaned || fallback
}

function hasHeaderFlag(headers: unknown, headerName: string, expectedValue: string): boolean {
  if (!headers) return false
  if (typeof headers === 'object' && headers !== null && 'get' in headers && typeof (headers as { get?: unknown }).get === 'function') {
    const value = (headers as { get: (name: string) => unknown }).get(headerName)
    return String(value || '') === expectedValue
  }
  if (typeof headers === 'object' && headers !== null) {
    const record = headers as Record<string, unknown>
    return String(record[headerName] ?? record[headerName.toLowerCase()] ?? '') === expectedValue
  }
  return false
}

function withRequestIdSuffix(message: string, requestId?: string): string {
  if (!requestId) return message
  return `${message} (request-id: ${requestId})`
}

function getRequestPath(url: unknown): string {
  if (typeof url !== 'string' || !url) return ''
  try {
    return new URL(url, window.location.origin).pathname
  } catch {
    return url
  }
}

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  // Long-running AI tasks (generation/graph/oasis) may exceed 2 minutes.
  timeout: 600000,
  headers: {
    'Content-Type': 'application/json',
  },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const { error: showError } = useToast()
    const requestId = error.response?.headers?.['x-request-id']
    const message = sanitizeErrorMessage(
      error.response?.data?.detail || error.response?.data?.message || error.message,
      'An unexpected error occurred'
    )
    const suppressAuthToast = hasHeaderFlag(error.config?.headers, 'X-Muse-Silent-Auth', '1')
    const requestPath = getRequestPath(error.config?.url)
    const isAuthStateRequest = requestPath === '/api/auth/me' || requestPath === '/api/auth/logout'
    const isAuthFormRequest = requestPath === '/api/auth/login' || requestPath === '/api/auth/register'
    const isSessionExpired = String(message).trim().toLowerCase() === 'session expired'

    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')

      if (suppressAuthToast) {
        return Promise.reject(error)
      }

      if (isAuthFormRequest) {
        showError(withRequestIdSuffix(message, requestId))
        return Promise.reject(error)
      }

      const currentPath = router.currentRoute.value.path || '/'
      const redirectTarget = currentPath.startsWith('/admin') ? '/admin/login' : '/login'
      router.push({ path: redirectTarget, query: { redirect: currentPath } })
      if (isSessionExpired || isAuthStateRequest) {
        showError(withRequestIdSuffix('Session expired. Please sign in again.', requestId))
      } else {
        showError(withRequestIdSuffix(message, requestId))
      }
    } else if (error.response?.status === 403) {
      showError(withRequestIdSuffix('You do not have permission to perform this action.', requestId))
    } else if (error.response?.status === 429) {
      showError(withRequestIdSuffix('Too many requests. Please try again later.', requestId))
    } else if (error.response?.status && error.response.status >= 500) {
      showError(withRequestIdSuffix('Server error. Please try again later.', requestId))
    } else {
      showError(withRequestIdSuffix(message, requestId))
    }

    return Promise.reject(error)
  }
)

export default api
