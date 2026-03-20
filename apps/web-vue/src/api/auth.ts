import api from './index'
import type { AuthResponse, User } from '@/types'

interface GetMeOptions {
  silentAuthFailure?: boolean
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  const { data } = await api.post<AuthResponse>('/api/auth/login', { email, password })
  return data
}

export async function register(
  email: string,
  password: string,
  nickname: string
): Promise<AuthResponse> {
  const { data } = await api.post<AuthResponse>('/api/auth/register', {
    email,
    password,
    nickname,
  })
  return data
}

export async function logout(): Promise<void> {
  await api.post('/api/auth/logout')
}

export async function getMe(options: GetMeOptions = {}): Promise<User> {
  const requestConfig = options.silentAuthFailure
    ? { headers: { 'X-Muse-Silent-Auth': '1' } }
    : null
  const { data } = requestConfig
    ? await api.get<User>('/api/auth/me', requestConfig)
    : await api.get<User>('/api/auth/me')
  return data
}
