<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { getBalance } from '@/api/billing'
import {
  LayoutDashboard,
  FolderOpen,
  Globe2,
  CreditCard,
  Settings,
  LogOut,
  Shield,
  Wallet,
  ChevronDown,
  Menu,
  X,
} from '@lucide/vue'
import ThemeModeSwitch from './ThemeModeSwitch.vue'
import LocaleSwitch from './LocaleSwitch.vue'
import PaletteSwitch from './PaletteSwitch.vue'
import MuseLogo from './MuseLogo.vue'
import Button from '@/components/ui/Button.vue'

const router = useRouter()
const route = useRoute()

watch(
  () => route.path,
  () => {
    showMobileNav.value = false
  },
)
const { t } = useI18n()
const authStore = useAuthStore()
const showUserMenu = ref(false)
const showMobileNav = ref(false)

const mainNavClass =
  'flex items-center gap-2 rounded-md px-3 py-2 text-sm text-stone-600 hover:bg-stone-200 hover:text-stone-900 transition-colors dark:text-stone-300 dark:hover:bg-zinc-800 dark:hover:text-stone-100'
const mainNavActiveClass = 'bg-stone-200 text-stone-900 dark:bg-zinc-800 dark:text-stone-100'

function closeMobileNav() {
  showMobileNav.value = false
}

function toggleMobileNav() {
  showMobileNav.value = !showMobileNav.value
  if (showMobileNav.value) {
    showUserMenu.value = false
  }
}
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
    showMobileNav.value = false
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
  <header class="sticky top-0 z-40 border-b border-stone-300/70 bg-[color:var(--muse-panel-strong)] dark:border-zinc-700/60 dark:bg-zinc-900/90">
    <div class="flex h-14 w-full min-w-0 items-center justify-between gap-2 px-3 sm:px-6 lg:px-8 2xl:px-10">
      <div class="flex min-w-0 flex-1 items-center gap-2 sm:gap-4 lg:gap-6">
        <router-link
          to="/dashboard"
          class="flex shrink-0 items-center gap-2 text-base font-bold text-stone-800 sm:text-lg dark:text-stone-100"
        >
          <MuseLogo size="sm" />
          <span class="hidden min-[380px]:inline">MuseGraph</span>
        </router-link>

        <nav v-if="authStore.isAuthenticated" class="hidden min-w-0 items-center gap-0.5 lg:flex">
          <router-link to="/dashboard" :class="mainNavClass" :active-class="mainNavActiveClass">
            <LayoutDashboard class="h-4 w-4 shrink-0" />
            <span class="whitespace-nowrap">{{ t('nav.dashboard') }}</span>
          </router-link>
          <router-link to="/projects" :class="mainNavClass" :active-class="mainNavActiveClass">
            <FolderOpen class="h-4 w-4 shrink-0" />
            <span class="whitespace-nowrap">{{ t('nav.projects') }}</span>
          </router-link>
          <router-link to="/plaza" :class="mainNavClass" :active-class="mainNavActiveClass">
            <Globe2 class="h-4 w-4 shrink-0" />
            <span class="whitespace-nowrap">{{ t('nav.plaza') }}</span>
          </router-link>
          <router-link to="/settings" :class="mainNavClass" :active-class="mainNavActiveClass">
            <Settings class="h-4 w-4 shrink-0" />
            <span class="whitespace-nowrap">{{ t('nav.settings') }}</span>
          </router-link>
          <router-link to="/pricing" :class="mainNavClass" :active-class="mainNavActiveClass">
            <CreditCard class="h-4 w-4 shrink-0" />
            <span class="whitespace-nowrap">{{ t('nav.pricing') }}</span>
          </router-link>
        </nav>
      </div>

      <div v-if="authStore.isAuthenticated" class="flex shrink-0 items-center gap-1 sm:gap-2">
        <button
          type="button"
          class="muse-icon-btn inline-flex h-8 w-8 items-center justify-center lg:hidden"
          :aria-expanded="showMobileNav"
          :aria-label="showMobileNav ? t('nav.closeMenu') : t('nav.menu')"
          @click="toggleMobileNav"
        >
          <Menu v-if="!showMobileNav" class="h-5 w-5" aria-hidden="true" />
          <X v-else class="h-5 w-5" aria-hidden="true" />
        </button>

        <LocaleSwitch />
        <ThemeModeSwitch />
        <PaletteSwitch />

        <div class="relative">
        <Button
          variant="ghost"
          size="sm"
          class="h-auto gap-1.5 px-1.5 py-1.5 text-sm text-stone-700 sm:px-3 dark:text-stone-300"
          @click="toggleMenu"
          @blur="delayedCloseMenu"
        >
          <div class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-600 text-xs font-medium text-white">
            {{ displayInitial }}
          </div>
          <span class="hidden max-w-[7rem] truncate md:inline">{{ displayName }}</span>
          <ChevronDown class="hidden h-4 w-4 sm:block" />
        </Button>

        <Transition
          enter-active-class="transition-all duration-150"
          leave-active-class="transition-all duration-150"
          enter-from-class="opacity-0 scale-95"
          leave-to-class="opacity-0 scale-95"
        >
          <div
            v-if="showUserMenu"
            class="muse-surface absolute right-0 mt-1 w-52 rounded-md py-1"
          >
            <div class="px-3 py-2 border-b border-stone-300 dark:border-zinc-700">
              <p class="text-sm font-medium text-stone-800 dark:text-stone-200">{{ displayName }}</p>
              <p class="text-xs text-stone-500 dark:text-stone-400">{{ authStore.user?.email }}</p>
            </div>
            <div class="px-3 py-2 border-b border-stone-300 dark:border-zinc-700">
              <p class="text-[11px] uppercase tracking-wide text-stone-500 dark:text-zinc-400">{{ t('nav.balance') }}</p>
              <p class="text-sm font-semibold text-stone-800 dark:text-stone-100">
                {{ balanceLoading ? t('common.loading') : formatUsd(displayBalance) }}
              </p>
            </div>

            <router-link
              to="/settings"
              class="flex items-center gap-2 px-3 py-2 text-sm text-stone-700 hover:bg-stone-200 hover:text-stone-900 dark:text-stone-300 dark:hover:bg-zinc-700 dark:hover:text-stone-100"
              @click="closeMenu"
            >
              <Settings class="w-4 h-4" />
              {{ t('nav.settings') }}
            </router-link>

            <router-link
              v-if="authStore.isAdmin"
              to="/admin"
              class="flex items-center gap-2 px-3 py-2 text-sm text-stone-700 hover:bg-stone-200 hover:text-stone-900 dark:text-stone-300 dark:hover:bg-zinc-700 dark:hover:text-stone-100"
              @click="closeMenu"
            >
              <Shield class="w-4 h-4" />
              {{ t('nav.admin') }}
            </router-link>

            <router-link
              to="/recharge"
              class="flex items-center gap-2 px-3 py-2 text-sm text-stone-700 hover:bg-stone-200 hover:text-stone-900 dark:text-stone-300 dark:hover:bg-zinc-700 dark:hover:text-stone-100"
              @click="closeMenu"
            >
              <Wallet class="w-4 h-4" />
              {{ t('nav.recharge') }}
            </router-link>

            <Button
              variant="ghost"
              size="sm"
              class="h-auto w-full justify-start px-3 py-2 text-sm text-red-600 hover:bg-stone-200 hover:text-red-700 dark:text-red-400 dark:hover:bg-zinc-700 dark:hover:text-red-300"
              @click="handleLogout"
            >
              <LogOut class="w-4 h-4" />
              {{ t('common.logout') }}
            </Button>
          </div>
        </Transition>
        </div>
      </div>

      <div v-else class="flex shrink-0 items-center gap-1 sm:gap-2">
        <LocaleSwitch />
        <ThemeModeSwitch />
        <PaletteSwitch />
        <router-link
          to="/login"
          class="rounded-md px-2 py-1.5 text-sm text-stone-700 hover:text-stone-900 transition-colors sm:px-3 dark:text-stone-300 dark:hover:text-stone-100"
        >
          {{ t('common.signIn') }}
        </router-link>
        <router-link
          to="/register"
          class="rounded-md bg-amber-600 px-2 py-1.5 text-sm text-white hover:bg-amber-700 transition-colors sm:px-3"
        >
          {{ t('common.signUp') }}
        </router-link>
      </div>
    </div>

    <Transition
      enter-active-class="transition-all duration-200 ease-out"
      leave-active-class="transition-all duration-150 ease-in"
      enter-from-class="opacity-0 -translate-y-1"
      leave-to-class="opacity-0 -translate-y-1"
    >
      <nav
        v-if="authStore.isAuthenticated && showMobileNav"
        class="border-t border-stone-300/70 px-3 py-2 lg:hidden dark:border-zinc-700/60"
      >
        <div class="grid gap-0.5">
          <router-link
            to="/dashboard"
            :class="mainNavClass"
            :active-class="mainNavActiveClass"
            @click="closeMobileNav"
          >
            <LayoutDashboard class="h-4 w-4 shrink-0" />
            {{ t('nav.dashboard') }}
          </router-link>
          <router-link
            to="/projects"
            :class="mainNavClass"
            :active-class="mainNavActiveClass"
            @click="closeMobileNav"
          >
            <FolderOpen class="h-4 w-4 shrink-0" />
            {{ t('nav.projects') }}
          </router-link>
          <router-link
            to="/plaza"
            :class="mainNavClass"
            :active-class="mainNavActiveClass"
            @click="closeMobileNav"
          >
            <Globe2 class="h-4 w-4 shrink-0" />
            {{ t('nav.plaza') }}
          </router-link>
          <router-link
            to="/settings"
            :class="mainNavClass"
            :active-class="mainNavActiveClass"
            @click="closeMobileNav"
          >
            <Settings class="h-4 w-4 shrink-0" />
            {{ t('nav.settings') }}
          </router-link>
          <router-link
            to="/pricing"
            :class="mainNavClass"
            :active-class="mainNavActiveClass"
            @click="closeMobileNav"
          >
            <CreditCard class="h-4 w-4 shrink-0" />
            {{ t('nav.pricing') }}
          </router-link>
        </div>
      </nav>
    </Transition>
  </header>
</template>
