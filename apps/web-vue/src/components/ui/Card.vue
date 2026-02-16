<script setup lang="ts">
defineProps<{
  padding?: boolean
}>()
</script>

<template>
  <div class="rounded-xl border border-slate-700/50 bg-slate-800/50 shadow-lg" :class="{ 'p-6': padding !== false }">
    <slot />
  </div>
</template>
