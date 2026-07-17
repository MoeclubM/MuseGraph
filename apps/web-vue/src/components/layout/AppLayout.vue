<script setup lang="ts">
withDefaults(
  defineProps<{
    padded?: boolean
  }>(),
  {
    padded: true,
  }
)

import AppHeader from './AppHeader.vue'
</script>

<template>
  <div class="muse-shell flex h-screen flex-col text-stone-900 dark:text-zinc-100">
    <AppHeader />
    <div class="flex flex-1 overflow-hidden">
      <slot name="sidebar" />
      <main class="flex-1 overflow-y-auto bg-transparent">
        <div :class="padded ? 'muse-layout-content' : 'h-full'">
          <slot />
        </div>
      </main>
    </div>
  </div>
</template>
