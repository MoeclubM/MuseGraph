import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/router', () => ({
  default: { push: vi.fn() },
}))

vi.mock('@/api/index', () => {
  return {
    default: {
      post: vi.fn(),
      get: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() },
      },
    },
  }
})

import api from '@/api/index'
import { login, register, logout, getMe } from '@/api/auth'
import type { AuthResponse, User } from '@/types'

const mockUser: User = {
  id: 'user-1',
  email: 'test@example.com',
  nickname: 'Test',
  avatar: null,
  balance: 0,
  is_admin: false,
  status: 'ACTIVE',
  created_at: '2024-01-01T00:00:00Z',
}

const mockAuthResponse: AuthResponse = {
  user: mockUser,
  token: 'mock-jwt-token',
}

describe('Auth API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('login', () => {
    it('should POST to /api/auth/login with email and password', async () => {
      vi.mocked(api.post).mockResolvedValue({ data: mockAuthResponse })

      const result = await login('test@example.com', 'password123')

      expect(api.post).toHaveBeenCalledWith('/api/auth/login', {
        email: 'test@example.com',
        password: 'password123',
      })
      expect(result).toEqual(mockAuthResponse)
    })

    it('should propagate error on failure', async () => {
      vi.mocked(api.post).mockRejectedValue(new Error('Invalid credentials'))

      await expect(login('bad@example.com', 'wrong')).rejects.toThrow('Invalid credentials')
    })
  })

  describe('register', () => {
    it('should POST to /api/auth/register with all fields', async () => {
      vi.mocked(api.post).mockResolvedValue({ data: mockAuthResponse })

      const result = await register('test@example.com', 'password123', 'Test')

      expect(api.post).toHaveBeenCalledWith('/api/auth/register', {
        email: 'test@example.com',
        password: 'password123',
        nickname: 'Test',
      })
      expect(result).toEqual(mockAuthResponse)
    })

    it('should propagate error on failure', async () => {
      vi.mocked(api.post).mockRejectedValue(new Error('Email already exists'))

      await expect(register('dup@example.com', 'pass', 'Dup')).rejects.toThrow('Email already exists')
    })
  })

  describe('logout', () => {
    it('should POST to /api/auth/logout', async () => {
      vi.mocked(api.post).mockResolvedValue({ data: undefined })

      await logout()

      expect(api.post).toHaveBeenCalledWith('/api/auth/logout')
    })

    it('should propagate error on failure', async () => {
      vi.mocked(api.post).mockRejectedValue(new Error('Server error'))

      await expect(logout()).rejects.toThrow('Server error')
    })
  })

  describe('getMe', () => {
    it('should GET /api/auth/me and return user', async () => {
      vi.mocked(api.get).mockResolvedValue({ data: mockUser })

      const result = await getMe()

      expect(api.get).toHaveBeenCalledWith('/api/auth/me')
      expect(result).toEqual(mockUser)
    })

    it('should pass silent auth header when requested', async () => {
      vi.mocked(api.get).mockResolvedValue({ data: mockUser })

      const result = await getMe({ silentAuthFailure: true })

      expect(api.get).toHaveBeenCalledWith('/api/auth/me', {
        headers: {
          'X-Muse-Silent-Auth': '1',
        },
      })
      expect(result).toEqual(mockUser)
    })

    it('should propagate error on failure', async () => {
      vi.mocked(api.get).mockRejectedValue(new Error('Unauthorized'))

      await expect(getMe()).rejects.toThrow('Unauthorized')
    })
  })
})
