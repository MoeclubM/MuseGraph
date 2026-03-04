<script setup lang="ts">
import { computed } from 'vue'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const alertVariants = cva(
  'relative w-full rounded-lg border px-4 py-3 text-sm',
  {
    variants: {
      variant: {
        default: 'border-stone-300/80 bg-stone-100/70 text-stone-700 dark:border-zinc-700/60 dark:bg-zinc-800/40 dark:text-zinc-200',
        warning: 'border-amber-700/30 bg-amber-900/10 text-amber-800 dark:text-amber-200',
        destructive: 'border-red-300/80 bg-red-100 text-red-700 dark:border-red-700/60 dark:bg-red-900/20 dark:text-red-300',
        success: 'border-emerald-700/30 bg-emerald-900/10 text-emerald-700 dark:text-emerald-200',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
)

type AlertVariant = VariantProps<typeof alertVariants>['variant']

const props = withDefaults(
  defineProps<{
    variant?: AlertVariant
  }>(),
  {
    variant: 'default',
  }
)

const classes = computed(() => cn(alertVariants({ variant: props.variant })))
</script>

<template>
  <div :class="classes">
    <slot />
  </div>
</template>
