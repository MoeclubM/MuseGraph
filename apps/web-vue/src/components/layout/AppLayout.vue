<script setup lang="ts">
import AppHeader from './AppHeader.vue'
</script>

<template>
  <div class="flex h-screen flex-col">
    <AppHeader />
    <div class="flex flex-1 overflow-hidden">
      <slot name="sidebar" />
      <main class="flex-1 overflow-y-auto">
        <slot />
      </main>
    </div>
  </div>
</template>
