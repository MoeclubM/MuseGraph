<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { getBalance } from '@/api/billing'
import {
  LayoutDashboard,
  FolderOpen,
  CreditCard,
  LogOut,
  Shield,
  Wallet,
  ChevronDown,
} from 'lucide-vue-next'
import ThemeModeSwitch from './ThemeModeSwitch.vue'
import Button from '@/components/ui/Button.vue'

const router = useRouter()
const authStore = useAuthStore()
const showUserMenu = ref(false)
const balanceLoading = ref(false)
const menuBalance = ref<number | null>(null)
const displayName = computed(() => authStore.user?.nickname || authStore.user?.email || 'User')
const displayInitial = computed(() => displayName.value.charAt(0).toUpperCase())
const displayBalance = computed(() => {
  if (menuBalance.value !== null) return menuBalance.value
  return authStore.user?.balance || 0
})

function formatUsd(value: number): string {
  return `$${Number(value || 0).toFixed(2)}`
}

async function refreshBalance() {
  if (!authStore.isAuthenticated) return
  balanceLoading.value = true
  try {
    const data = await getBalance()
    menuBalance.value = data.balance || 0
    authStore.setBalance(menuBalance.value)
  } finally {
    balanceLoading.value = false
  }
}

function toggleMenu() {
  showUserMenu.value = !showUserMenu.value
  if (showUserMenu.value) {
    void refreshBalance()
  }
}

function closeMenu() {
  showUserMenu.value = false
}

function delayedCloseMenu() {
  setTimeout(closeMenu, 150)
}

async function handleLogout() {
  await authStore.logout()
  menuBalance.value = null
  router.push('/login')
}
</script>

<template>
  <header class="sticky top-0 z-40 border-b border-stone-300/70 bg-[color:var(--muse-panel-strong)] backdrop-blur-md dark:border-zinc-700/60 dark:bg-zinc-900/90">
    <div class="flex h-14 w-full items-center justify-between px-2 sm:px-3">
      <div class="flex items-center gap-6">
        <router-link to="/dashboard" class="flex items-center gap-2 text-lg font-bold text-stone-800 dark:text-stone-100">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-amber-500 to-amber-700 shadow-[0_8px_18px_rgba(217,119,6,0.35)]">
            <span class="text-sm font-bold text-white">M</span>
          </div>
          MuseGraph
        </router-link>

        <nav v-if="authStore.isAuthenticated" class="hidden sm:flex items-center gap-1">
          <router-link
            to="/dashboard"
            class="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-stone-600 hover:bg-stone-200 hover:text-stone-900 transition-colors dark:text-stone-300 dark:hover:bg-zinc-800 dark:hover:text-stone-100"
            active-class="bg-stone-200 text-stone-900 dark:bg-zinc-800 dark:text-stone-100"
          >
            <LayoutDashboard class="w-4 h-4" />
            Dashboard
          </router-link>
          <router-link
            to="/projects"
            class="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-stone-600 hover:bg-stone-200 hover:text-stone-900 transition-colors dark:text-stone-300 dark:hover:bg-zinc-800 dark:hover:text-stone-100"
            active-class="bg-stone-200 text-stone-900 dark:bg-zinc-800 dark:text-stone-100"
          >
            <FolderOpen class="w-4 h-4" />
            Projects
          </router-link>
          <router-link
            to="/pricing"
            class="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-stone-600 hover:bg-stone-200 hover:text-stone-900 transition-colors dark:text-stone-300 dark:hover:bg-zinc-800 dark:hover:text-stone-100"
            active-class="bg-stone-200 text-stone-900 dark:bg-zinc-800 dark:text-stone-100"
          >
            <CreditCard class="w-4 h-4" />
            Pricing
          </router-link>
        </nav>
      </div>

      <div v-if="authStore.isAuthenticated" class="flex items-center gap-2">
        <ThemeModeSwitch />

        <div class="relative">
        <Button
          variant="ghost"
          size="sm"
          class="h-auto px-3 py-1.5 text-sm text-stone-700 dark:text-stone-300"
          @click="toggleMenu"
          @blur="delayedCloseMenu"
        >
          <div class="flex h-7 w-7 items-center justify-center rounded-full bg-amber-600 text-xs font-medium text-white">
            {{ displayInitial }}
          </div>
          <span class="hidden sm:inline">{{ displayName }}</span>
          <ChevronDown class="w-4 h-4" />
        </Button>

        <Transition
          enter-active-class="transition-all duration-150"
          leave-active-class="transition-all duration-150"
          enter-from-class="opacity-0 scale-95"
          leave-to-class="opacity-0 scale-95"
        >
          <div
            v-if="showUserMenu"
            class="muse-surface absolute right-0 mt-1 w-52 rounded-xl py-1"
          >
            <div class="px-3 py-2 border-b border-stone-300 dark:border-zinc-700">
              <p class="text-sm font-medium text-stone-800 dark:text-stone-200">{{ displayName }}</p>
              <p class="text-xs text-stone-500 dark:text-stone-400">{{ authStore.user?.email }}</p>
            </div>
            <div class="px-3 py-2 border-b border-stone-300 dark:border-zinc-700">
              <p class="text-[11px] uppercase tracking-wide text-stone-500 dark:text-zinc-400">Balance</p>
              <p class="text-sm font-semibold text-stone-800 dark:text-stone-100">
                {{ balanceLoading ? 'Loading...' : formatUsd(displayBalance) }}
              </p>
            </div>

            <router-link
              v-if="authStore.isAdmin"
              to="/admin"
              class="flex items-center gap-2 px-3 py-2 text-sm text-stone-700 hover:bg-stone-200 hover:text-stone-900 dark:text-stone-300 dark:hover:bg-zinc-700 dark:hover:text-stone-100"
              @click="closeMenu"
            >
              <Shield class="w-4 h-4" />
              Admin Panel
            </router-link>

            <router-link
              to="/recharge"
              class="flex items-center gap-2 px-3 py-2 text-sm text-stone-700 hover:bg-stone-200 hover:text-stone-900 dark:text-stone-300 dark:hover:bg-zinc-700 dark:hover:text-stone-100"
              @click="closeMenu"
            >
              <Wallet class="w-4 h-4" />
              Recharge
            </router-link>

            <Button
              variant="ghost"
              size="sm"
              class="h-auto w-full justify-start px-3 py-2 text-sm text-red-600 hover:bg-stone-200 hover:text-red-700 dark:text-red-400 dark:hover:bg-zinc-700 dark:hover:text-red-300"
              @click="handleLogout"
            >
              <LogOut class="w-4 h-4" />
              Logout
            </Button>
          </div>
        </Transition>
        </div>
      </div>

      <div v-else class="flex items-center gap-2">
        <ThemeModeSwitch />
        <router-link
          to="/login"
          class="rounded-lg px-3 py-1.5 text-sm text-stone-700 hover:text-stone-900 transition-colors dark:text-stone-300 dark:hover:text-stone-100"
        >
          Sign In
        </router-link>
        <router-link
          to="/register"
          class="rounded-lg bg-amber-600 px-3 py-1.5 text-sm text-white hover:bg-amber-700 transition-colors"
        >
          Sign Up
        </router-link>
      </div>
    </div>
  </header>
</template>
