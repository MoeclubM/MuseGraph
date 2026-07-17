<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { Shield, Home, LogOut } from '@lucide/vue'
import ThemeModeSwitch from './ThemeModeSwitch.vue'
import LocaleSwitch from './LocaleSwitch.vue'
import Button from '@/components/ui/Button.vue'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()

const navItems = computed(() => [
  { to: '/admin', label: t('admin.nav.panel'), exact: true },
  { to: '/admin/orders', label: t('admin.nav.orders'), exact: false },
  { to: '/admin/usage', label: t('admin.nav.usage'), exact: false },
])

function navLinkClass(to: string, exact: boolean) {
  const active = exact ? route.path === to : route.path.startsWith(to)
  return [
    'rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
    active
      ? 'bg-amber-600/15 text-amber-800 dark:bg-amber-500/20 dark:text-amber-200'
      : 'text-stone-600 hover:bg-stone-200/80 hover:text-stone-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100',
  ]
}
const authStore = useAuthStore()
const displayName = computed(
  () => authStore.user?.nickname || authStore.user?.email || t('admin.layout.displayNameFallback'),
)

async function handleLogout() {
  await authStore.logout()
  router.push('/admin/login')
}
</script>

<template>
  <div class="muse-shell flex min-h-screen flex-col text-stone-900 dark:text-stone-100">
    <header class="sticky top-0 z-40 border-b border-stone-300/70 bg-[color:var(--muse-panel-strong)] dark:border-zinc-700/60 dark:bg-zinc-900/90">
      <div class="flex h-14 w-full min-w-0 items-center justify-between gap-2 px-3 sm:px-6 lg:px-8 2xl:px-10">
        <div class="flex min-w-0 items-center gap-2 sm:gap-3">
          <div class="flex h-8 w-8 items-center justify-center rounded-md bg-amber-600">
            <Shield class="h-4 w-4" />
          </div>
          <div>
            <p class="text-sm font-semibold leading-none">{{ t('admin.layout.title') }}</p>
            <p class="text-[11px] muse-text-muted">{{ displayName }}</p>
          </div>
        </div>
        <div class="flex shrink-0 items-center gap-1 sm:gap-2">
          <LocaleSwitch />
          <ThemeModeSwitch />
          <Button
            variant="secondary"
            size="sm"
            class="h-8 px-2 text-xs sm:px-3"
            :title="t('admin.layout.front')"
            @click="router.push('/dashboard')"
          >
            <Home class="h-3.5 w-3.5" />
            <span class="hidden sm:inline">{{ t('admin.layout.front') }}</span>
          </Button>
          <Button
            variant="secondary"
            size="sm"
            class="h-8 px-2 text-xs sm:px-3"
            :title="t('admin.layout.logout')"
            @click="handleLogout"
          >
            <LogOut class="h-3.5 w-3.5" />
            <span class="hidden sm:inline">{{ t('admin.layout.logout') }}</span>
          </Button>
        </div>
      </div>
    </header>
    <nav class="border-b border-stone-300/70 bg-[color:var(--muse-panel)] px-3 py-2 sm:px-6 lg:px-8 2xl:px-10 dark:border-zinc-700/60">
      <div class="flex flex-wrap gap-2">
        <router-link
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          :class="navLinkClass(item.to, item.exact)"
        >
          {{ item.label }}
        </router-link>
      </div>
    </nav>
    <main class="w-full flex-1 space-y-6 px-4 py-5 sm:px-6 sm:py-6 lg:px-8 2xl:px-10">
      <slot />
    </main>
  </div>
</template>
