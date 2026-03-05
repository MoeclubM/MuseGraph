<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { Shield, Home, LogOut } from 'lucide-vue-next'
import ThemeModeSwitch from './ThemeModeSwitch.vue'
import Button from '@/components/ui/Button.vue'

const router = useRouter()
const authStore = useAuthStore()
const displayName = computed(() => authStore.user?.nickname || authStore.user?.email || 'Admin')

async function handleLogout() {
  await authStore.logout()
  router.push('/admin/login')
}
</script>

<template>
  <div class="muse-shell flex min-h-screen flex-col text-stone-900 dark:text-stone-100">
    <header class="sticky top-0 z-40 border-b border-stone-300/70 bg-[color:var(--muse-panel-strong)] backdrop-blur dark:border-zinc-700/60 dark:bg-zinc-900/90">
      <div class="flex h-14 w-full items-center justify-between px-2 sm:px-3">
        <div class="flex items-center gap-3">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-amber-500 to-amber-700 shadow-[0_8px_18px_rgba(217,119,6,0.35)]">
            <Shield class="h-4 w-4" />
          </div>
          <div>
            <p class="text-sm font-semibold leading-none">MuseGraph Admin</p>
            <p class="text-[11px] text-stone-500 dark:text-stone-400">{{ displayName }}</p>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <ThemeModeSwitch />
          <Button
            variant="secondary"
            size="sm"
            class="h-8 px-3 text-xs"
            @click="router.push('/dashboard')"
          >
            <Home class="h-3.5 w-3.5" />
            Front
          </Button>
          <Button
            variant="secondary"
            size="sm"
            class="h-8 px-3 text-xs"
            @click="handleLogout"
          >
            <LogOut class="h-3.5 w-3.5" />
            Logout
          </Button>
        </div>
      </div>
    </header>
    <main class="mx-auto w-full max-w-7xl flex-1 space-y-6 px-4 py-5 sm:px-6 sm:py-6 lg:px-8">
      <slot />
    </main>
  </div>
</template>
