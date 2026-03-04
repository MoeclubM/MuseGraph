import api from './index'
import type { AuthResponse, User } from '@/types'

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

export async function getMe(): Promise<User> {
  const { data } = await api.get<User>('/api/auth/me')
  return data
}
