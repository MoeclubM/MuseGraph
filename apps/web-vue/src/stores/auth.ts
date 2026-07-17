import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { User } from '@/types'
import * as authApi from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const initialized = ref(false)

  const isAuthenticated = computed(() => user.value !== null)
  const isAdmin = computed(() => !!user.value?.is_admin)

  function clearSession() {
    user.value = null
  }

  async function init() {
    try {
      user.value = await authApi.getMe({ silentAuthFailure: true })
    } catch {
      clearSession()
    } finally {
      initialized.value = true
    }
  }

  async function login(email: string, password: string) {
    user.value = (await authApi.login(email, password)).user
  }

  async function register(email: string, password: string, nickname: string) {
    user.value = (await authApi.register(email, password, nickname)).user
  }

  async function fetchMe(options?: { silentAuthFailure?: boolean }) {
    user.value = await authApi.getMe(options)
  }

  function setBalance(balance: number) {
    if (user.value) user.value = { ...user.value, balance }
  }

  async function logout() {
    await authApi.logout()
    clearSession()
  }

  async function updateUser(payload: { nickname?: string; email?: string }) {
    user.value = await authApi.updateMe(payload)
  }

  async function changePassword(payload: { current_password: string; new_password: string }) {
    await authApi.changePassword(payload)
    clearSession()
  }

  return {
    user,
    initialized,
    isAuthenticated,
    isAdmin,
    init,
    login,
    register,
    fetchMe,
    setBalance,
    updateUser,
    changePassword,
    logout,
  }
})
