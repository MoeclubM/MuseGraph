<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {
  LayoutDashboard,
  CreditCard,
  LogOut,
  Shield,
  Wallet,
  ChevronDown,
  User,
} from 'lucide-vue-next'

const router = useRouter()
const authStore = useAuthStore()
const showUserMenu = ref(false)

function toggleMenu() {
  showUserMenu.value = !showUserMenu.value
}

function closeMenu() {
  showUserMenu.value = false
}

function delayedCloseMenu() {
  setTimeout(closeMenu, 150)
}

async function handleLogout() {
  await authStore.logout()
  router.push('/login')
}
</script>

<template>
  <header class="sticky top-0 z-40 border-b border-slate-700/50 bg-slate-900/80 backdrop-blur-md">
    <div class="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6">
      <div class="flex items-center gap-6">
        <router-link to="/dashboard" class="flex items-center gap-2 text-lg font-bold text-white">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600">
            <span class="text-sm font-bold">M</span>
          </div>
          MuseGraph
        </router-link>

        <nav v-if="authStore.isAuthenticated" class="hidden sm:flex items-center gap-1">
          <router-link
            to="/dashboard"
            class="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
            active-class="bg-slate-800 text-white"
          >
            <LayoutDashboard class="w-4 h-4" />
            Dashboard
          </router-link>
          <router-link
            to="/pricing"
            class="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
            active-class="bg-slate-800 text-white"
          >
            <CreditCard class="w-4 h-4" />
            Pricing
          </router-link>
        </nav>
      </div>

      <div v-if="authStore.isAuthenticated" class="relative">
        <button
          class="flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
          @click="toggleMenu"
          @blur="delayedCloseMenu"
        >
          <div class="flex h-7 w-7 items-center justify-center rounded-full bg-blue-600 text-xs font-medium text-white">
            {{ authStore.user?.username?.charAt(0)?.toUpperCase() || 'U' }}
          </div>
          <span class="hidden sm:inline">{{ authStore.user?.nickname || authStore.user?.username }}</span>
          <ChevronDown class="w-4 h-4" />
        </button>

        <Transition
          enter-active-class="transition-all duration-150"
          leave-active-class="transition-all duration-150"
          enter-from-class="opacity-0 scale-95"
          leave-to-class="opacity-0 scale-95"
        >
          <div
            v-if="showUserMenu"
            class="absolute right-0 mt-1 w-48 rounded-lg border border-slate-700 bg-slate-800 py-1 shadow-xl"
          >
            <div class="px-3 py-2 border-b border-slate-700">
              <p class="text-sm font-medium text-slate-200">{{ authStore.user?.username }}</p>
              <p class="text-xs text-slate-400">{{ authStore.user?.email }}</p>
            </div>

            <router-link
              v-if="authStore.isAdmin"
              to="/admin"
              class="flex items-center gap-2 px-3 py-2 text-sm text-slate-300 hover:bg-slate-700 hover:text-white"
              @click="closeMenu"
            >
              <Shield class="w-4 h-4" />
              Admin Panel
            </router-link>

            <router-link
              to="/recharge"
              class="flex items-center gap-2 px-3 py-2 text-sm text-slate-300 hover:bg-slate-700 hover:text-white"
              @click="closeMenu"
            >
              <Wallet class="w-4 h-4" />
              Recharge
            </router-link>

            <button
              class="flex w-full items-center gap-2 px-3 py-2 text-sm text-red-400 hover:bg-slate-700 hover:text-red-300"
              @click="handleLogout"
            >
              <LogOut class="w-4 h-4" />
              Logout
            </button>
          </div>
        </Transition>
      </div>

      <div v-else class="flex items-center gap-2">
        <router-link
          to="/login"
          class="rounded-lg px-3 py-1.5 text-sm text-slate-300 hover:text-white transition-colors"
        >
          Sign In
        </router-link>
        <router-link
          to="/register"
          class="rounded-lg bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 transition-colors"
        >
          Sign Up
        </router-link>
      </div>
    </div>
  </header>
</template>
