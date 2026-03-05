<script setup lang="ts">
import { computed } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  padding?: boolean
  stack?: boolean
}>()

const classes = computed(() =>
  cn(
    'muse-surface rounded-2xl overflow-hidden',
    props.padding !== false && 'p-4 sm:p-5',
    props.stack !== false && 'card-stack'
  )
)
</script>

<template>
  <div :class="classes">
    <slot />
  </div>
</template>

<style scoped>
.card-stack > * + * {
  margin-top: 0.875rem;
}
</style>
