import axios from 'axios'
import router from '@/router'
import { useToast } from '@/composables/useToast'

function withRequestIdSuffix(message: string, requestId?: string): string {
  if (!requestId) return message
  return `${message} (request-id: ${requestId})`
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
    const message = error.response?.data?.detail || error.response?.data?.message || error.message || 'An unexpected error occurred'

    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      const currentPath = router.currentRoute.value.path || '/'
      const redirectTarget = currentPath.startsWith('/admin') ? '/admin/login' : '/login'
      router.push({ path: redirectTarget, query: { redirect: currentPath } })
      showError(withRequestIdSuffix('Session expired. Please sign in again.', requestId))
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
