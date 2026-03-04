import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'

vi.mock('@/api/auth', () => ({
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  getMe: vi.fn(),
}))

import * as authApi from '@/api/auth'

const mockUser = {
  id: 'user-1',
  email: 'test@example.com',
  nickname: 'Test',
  avatar: null,
  balance: 0,
  is_admin: false,
  status: 'ACTIVE' as const,
  created_at: '2024-01-01T00:00:00Z',
}

const mockAuthResponse = {
  user: mockUser,
  token: 'mock-jwt-token',
}

describe('Auth Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    localStorage.clear()
  })

  describe('initial state', () => {
    it('should have null user and token', () => {
      const store = useAuthStore()
      expect(store.user).toBeNull()
      expect(store.token).toBeNull()
    })

    it('should not be authenticated', () => {
      const store = useAuthStore()
      expect(store.isAuthenticated).toBe(false)
    })

    it('should not be admin', () => {
      const store = useAuthStore()
      expect(store.isAdmin).toBe(false)
    })
  })

  describe('login', () => {
    it('should set user and token on successful login', async () => {
      vi.mocked(authApi.login).mockResolvedValue(mockAuthResponse)

      const store = useAuthStore()
      await store.login('test@example.com', 'password123')

      expect(authApi.login).toHaveBeenCalledWith('test@example.com', 'password123')
      expect(store.user).toEqual(mockUser)
      expect(store.token).toBe('mock-jwt-token')
    })

    it('should persist token and user to localStorage', async () => {
      vi.mocked(authApi.login).mockResolvedValue(mockAuthResponse)

      const store = useAuthStore()
      await store.login('test@example.com', 'password123')

      expect(localStorage.getItem('token')).toBe('mock-jwt-token')
      expect(localStorage.getItem('user')).toBe(JSON.stringify(mockUser))
    })

    it('should set isAuthenticated to true after login', async () => {
      vi.mocked(authApi.login).mockResolvedValue(mockAuthResponse)

      const store = useAuthStore()
      await store.login('test@example.com', 'password123')

      expect(store.isAuthenticated).toBe(true)
    })

    it('should propagate error on failed login', async () => {
      vi.mocked(authApi.login).mockRejectedValue(new Error('Invalid credentials'))

      const store = useAuthStore()
      await expect(store.login('bad@example.com', 'wrong')).rejects.toThrow('Invalid credentials')
      expect(store.user).toBeNull()
      expect(store.token).toBeNull()
    })
  })

  describe('logout', () => {
    it('should clear user and token', async () => {
      vi.mocked(authApi.login).mockResolvedValue(mockAuthResponse)
      vi.mocked(authApi.logout).mockResolvedValue(undefined)

      const store = useAuthStore()
      await store.login('test@example.com', 'password123')
      await store.logout()

      expect(store.user).toBeNull()
      expect(store.token).toBeNull()
      expect(store.isAuthenticated).toBe(false)
    })

    it('should remove token and user from localStorage', async () => {
      vi.mocked(authApi.login).mockResolvedValue(mockAuthResponse)
      vi.mocked(authApi.logout).mockResolvedValue(undefined)

      const store = useAuthStore()
      await store.login('test@example.com', 'password123')
      await store.logout()

      expect(localStorage.getItem('token')).toBeNull()
      expect(localStorage.getItem('user')).toBeNull()
    })

    it('should still clear state even if API call fails', async () => {
      vi.mocked(authApi.login).mockResolvedValue(mockAuthResponse)
      vi.mocked(authApi.logout).mockRejectedValue(new Error('Network error'))

      const store = useAuthStore()
      await store.login('test@example.com', 'password123')
      await store.logout()

      expect(store.user).toBeNull()
      expect(store.token).toBeNull()
    })
  })

  describe('fetchMe', () => {
    it('should update user from API', async () => {
      vi.mocked(authApi.getMe).mockResolvedValue(mockUser)

      const store = useAuthStore()
      await store.fetchMe()

      expect(store.user).toEqual(mockUser)
    })

    it('should persist updated user to localStorage', async () => {
      vi.mocked(authApi.getMe).mockResolvedValue(mockUser)

      const store = useAuthStore()
      await store.fetchMe()

      expect(localStorage.getItem('user')).toBe(JSON.stringify(mockUser))
    })

    it('should propagate error on failure', async () => {
      vi.mocked(authApi.getMe).mockRejectedValue(new Error('Unauthorized'))

      const store = useAuthStore()
      await expect(store.fetchMe()).rejects.toThrow('Unauthorized')
    })
  })

  describe('isAuthenticated', () => {
    it('should return false when no token', () => {
      const store = useAuthStore()
      expect(store.isAuthenticated).toBe(false)
    })

    it('should return true when token is set', async () => {
      vi.mocked(authApi.login).mockResolvedValue(mockAuthResponse)

      const store = useAuthStore()
      await store.login('test@example.com', 'password123')

      expect(store.isAuthenticated).toBe(true)
    })

    it('should return false after logout', async () => {
      vi.mocked(authApi.login).mockResolvedValue(mockAuthResponse)
      vi.mocked(authApi.logout).mockResolvedValue(undefined)

      const store = useAuthStore()
      await store.login('test@example.com', 'password123')
      await store.logout()

      expect(store.isAuthenticated).toBe(false)
    })
  })

  describe('isAdmin', () => {
    it('should return true when user is admin', async () => {
      const adminResponse = {
        user: { ...mockUser, is_admin: true },
        token: 'admin-token',
      }
      vi.mocked(authApi.login).mockResolvedValue(adminResponse)

      const store = useAuthStore()
      await store.login('admin@example.com', 'password123')

      expect(store.isAdmin).toBe(true)
    })

    it('should return false when user is not admin', async () => {
      vi.mocked(authApi.login).mockResolvedValue(mockAuthResponse)

      const store = useAuthStore()
      await store.login('test@example.com', 'password123')

      expect(store.isAdmin).toBe(false)
    })
  })
})
