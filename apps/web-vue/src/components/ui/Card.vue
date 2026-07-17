<script setup lang="ts">
import { computed, useAttrs } from 'vue'
import { cn } from '@/lib/utils'

defineOptions({
  inheritAttrs: false,
})

const props = withDefaults(
  defineProps<{
    padding?: boolean
    stack?: boolean
    variant?: 'default' | 'stat' | 'interactive' | 'highlight' | 'inset' | 'compact' | 'flush'
  }>(),
  {
    padding: true,
    stack: true,
    variant: 'default',
  },
)

const attrs = useAttrs()

const classes = computed(() => {
  const { variant, padding, stack } = props
  const usesDefaultPadding = padding && (variant === 'default' || variant === 'highlight' || variant === 'inset')

  return cn(
    'muse-card overflow-hidden rounded-md',
    variant === 'stat' && 'muse-card-stat',
    variant === 'interactive' && 'muse-card-interactive-tile',
    variant === 'highlight' && 'muse-card-highlight',
    variant === 'inset' && 'muse-card-inset',
    variant === 'compact' && 'muse-card-compact',
    usesDefaultPadding && 'p-5 sm:p-6',
    stack && !['stat', 'interactive', 'compact', 'flush'].includes(variant) && 'card-stack',
    variant === 'interactive' && 'card-stack',
    attrs.class as string | undefined,
  )
})
</script>

<template>
  <div v-bind="attrs" :class="classes">
    <slot />
  </div>
</template>

<style scoped>
.card-stack > * + * {
  margin-top: 1rem;
}
</style>
