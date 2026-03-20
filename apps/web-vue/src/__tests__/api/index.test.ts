import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'

const { push, showError } = vi.hoisted(() => ({
  push: vi.fn(),
  showError: vi.fn(),
}))

vi.mock('@/router', () => ({
  default: {
    currentRoute: {
      value: {
        path: '/login',
      },
    },
    push,
  },
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    error: showError,
  }),
}))

import api from '@/api/index'

function buildUnauthorizedResponse(
  config: InternalAxiosRequestConfig,
  detail: string,
  requestId = 'req-123'
): AxiosResponse {
  return {
    data: { detail },
    status: 401,
    statusText: 'Unauthorized',
    headers: {
      'x-request-id': requestId,
    },
    config,
  }
}

describe('API interceptor', () => {
  const originalAdapter = api.defaults.adapter

  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    push.mockReset()
    showError.mockReset()
  })

  afterEach(() => {
    api.defaults.adapter = originalAdapter
  })

  it('shows the backend login error instead of session-expired for login 401s', async () => {
    api.defaults.adapter = async (config) => {
      throw new AxiosError(
        'Request failed with status code 401',
        'ERR_BAD_REQUEST',
        config,
        undefined,
        buildUnauthorizedResponse(config, 'Invalid credentials', 'login-401')
      )
    }

    await expect(api.post('/api/auth/login', { email: 'admin@example.com', password: 'wrongpass' })).rejects.toBeInstanceOf(AxiosError)

    expect(showError).toHaveBeenCalledWith('Invalid credentials (request-id: login-401)')
    expect(push).not.toHaveBeenCalled()
  })

  it('suppresses redirect and toast for silent auth bootstrap failures', async () => {
    localStorage.setItem('token', 'stale-token')
    localStorage.setItem('user', JSON.stringify({ id: 'user-1' }))

    api.defaults.adapter = async (config) => {
      throw new AxiosError(
        'Request failed with status code 401',
        'ERR_BAD_REQUEST',
        config,
        undefined,
        buildUnauthorizedResponse(config, 'Session expired', 'silent-401')
      )
    }

    await expect(
      api.get('/api/auth/me', {
        headers: {
          'X-Muse-Silent-Auth': '1',
        },
      })
    ).rejects.toBeInstanceOf(AxiosError)

    expect(showError).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()
    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('user')).toBeNull()
  })
})
