<script setup lang="ts">
import { computed } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  padding?: boolean
  stack?: boolean
}>()

const classes = computed(() =>
  cn(
    'rounded-lg border border-stone-300/80 bg-stone-50/95 shadow-sm overflow-hidden dark:border-zinc-700/60 dark:bg-zinc-800/70',
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
