<script setup lang="ts">
defineProps<{
  label: string
  description?: string
  htmlFor?: string
}>()
</script>

<template>
  <div class="space-y-1.5">
    <label
      v-if="htmlFor"
      :for="htmlFor"
      class="block text-sm font-medium muse-text-body"
    >
      {{ label }}
    </label>
    <p v-else class="text-sm font-medium muse-text-body">
      {{ label }}
    </p>
    <p v-if="description" class="text-xs muse-text-muted">
      {{ description }}
    </p>
    <slot />
  </div>
</template>