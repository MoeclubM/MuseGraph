import axios from 'axios'
import router from '@/router'
import { useToast } from '@/composables/useToast'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  timeout: 120000,
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
    const message = error.response?.data?.detail || error.response?.data?.message || error.message || 'An unexpected error occurred'

    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      router.push('/login')
      showError('Session expired. Please sign in again.')
    } else if (error.response?.status === 403) {
      showError('You do not have permission to perform this action.')
    } else if (error.response?.status === 429) {
      showError('Too many requests. Please try again later.')
    } else if (error.response?.status && error.response.status >= 500) {
      showError('Server error. Please try again later.')
    } else {
      showError(message)
    }

    return Promise.reject(error)
  }
)

export default api
