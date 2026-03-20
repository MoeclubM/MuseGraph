import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User } from '@/types'
import * as authApi from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const token = ref<string | null>(null)

  const isAuthenticated = computed(() => !!token.value)
  const isAdmin = computed(() => !!user.value?.is_admin)

  function clearLocalSession() {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  function init() {
    const savedToken = localStorage.getItem('token')
    const savedUser = localStorage.getItem('user')
    const currentPath = window.location.pathname || '/'
    const isGuestPath = currentPath === '/login' || currentPath === '/register' || currentPath === '/admin/login'
    if (savedToken) {
      if (!isGuestPath) {
        token.value = savedToken
      }
      if (savedUser && !isGuestPath) {
        try {
          user.value = JSON.parse(savedUser)
        } catch {
          user.value = null
        }
      }
      fetchMe({ silentAuthFailure: true })
        .then(() => {
          token.value = savedToken
        })
        .catch(() => {
          clearLocalSession()
        })
    }
  }

  async function login(email: string, password: string) {
    const res = await authApi.login(email, password)
    token.value = res.token
    user.value = res.user
    localStorage.setItem('token', res.token)
    localStorage.setItem('user', JSON.stringify(res.user))
  }

  async function register(email: string, password: string, nickname: string) {
    const res = await authApi.register(email, password, nickname)
    token.value = res.token
    user.value = res.user
    localStorage.setItem('token', res.token)
    localStorage.setItem('user', JSON.stringify(res.user))
  }

  async function fetchMe(options?: { silentAuthFailure?: boolean }) {
    const me = await authApi.getMe(options)
    user.value = me
    localStorage.setItem('user', JSON.stringify(me))
  }

  function setBalance(balance: number) {
    if (!user.value) return
    user.value = {
      ...user.value,
      balance,
    }
    localStorage.setItem('user', JSON.stringify(user.value))
  }

  async function logout() {
    try {
      await authApi.logout()
    } catch {
      // ignore
    }
    clearLocalSession()
  }

  return {
    user,
    token,
    isAuthenticated,
    isAdmin,
    init,
    login,
    register,
    fetchMe,
    setBalance,
    logout,
  }
})
