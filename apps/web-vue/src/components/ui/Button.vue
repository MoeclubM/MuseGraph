<script setup lang="ts">
import { computed } from 'vue'
import { Loader2 } from 'lucide-vue-next'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-[color,box-shadow] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/60 disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        primary: 'bg-amber-600 text-white shadow-sm hover:bg-amber-700',
        secondary: 'border border-stone-300 bg-stone-100 text-stone-800 shadow-sm hover:bg-stone-200 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100 dark:hover:bg-zinc-700',
        danger: 'bg-red-600 text-white shadow-sm hover:bg-red-700 focus-visible:ring-red-500/60',
        ghost: 'bg-transparent text-stone-700 hover:bg-stone-200 hover:text-stone-900 dark:text-zinc-200 dark:hover:bg-zinc-800 dark:hover:text-zinc-100',
      },
      size: {
        sm: 'h-8 px-3 text-xs',
        md: 'h-9 px-4 py-2',
        lg: 'h-10 px-6',
      },
    },
    defaultVariants: {
      variant: 'primary',
      size: 'md',
    },
  }
)

type ButtonVariant = VariantProps<typeof buttonVariants>['variant']
type ButtonSize = VariantProps<typeof buttonVariants>['size']

const props = withDefaults(
  defineProps<{
    variant?: ButtonVariant
    size?: ButtonSize
    loading?: boolean
    disabled?: boolean
    type?: 'button' | 'submit' | 'reset'
  }>(),
  {
    variant: 'primary',
    size: 'md',
    loading: false,
    disabled: false,
    type: 'button',
  }
)

const classes = computed(() => {
  return cn(
    buttonVariants({
      variant: props.variant,
      size: props.size,
    })
  )
})
</script>

<template>
  <button
    :type="type"
    :class="classes"
    :disabled="disabled || loading"
  >
    <Loader2 v-if="loading" class="w-4 h-4 animate-spin" />
    <slot />
  </button>
</template>

