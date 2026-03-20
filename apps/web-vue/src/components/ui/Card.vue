<script setup lang="ts">
import { computed } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  padding?: boolean
  stack?: boolean
}>()

const classes = computed(() =>
  cn(
    'muse-surface overflow-hidden rounded-md',
    props.padding !== false && 'p-5 sm:p-6',
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
  margin-top: 1rem;
}
</style>
