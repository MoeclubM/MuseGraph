<script setup lang="ts">
import { computed } from 'vue'
import { Loader2 } from 'lucide-vue-next'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-medium transition-all duration-200 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-amber-500/35 focus-visible:ring-offset-2 focus-visible:ring-offset-transparent disabled:pointer-events-none disabled:opacity-50 active:scale-[0.985]',
  {
    variants: {
      variant: {
        primary: 'border border-amber-600 bg-gradient-to-b from-amber-500 to-amber-600 text-white shadow-[0_8px_18px_rgba(217,119,6,0.28)] hover:from-amber-500 hover:to-amber-700',
        secondary: 'border border-stone-300/90 bg-stone-100/90 text-stone-800 shadow-sm hover:bg-stone-200/95 dark:border-zinc-700 dark:bg-zinc-800/90 dark:text-zinc-100 dark:hover:bg-zinc-700/90',
        danger: 'border border-red-600 bg-gradient-to-b from-red-500 to-red-600 text-white shadow-[0_8px_18px_rgba(220,38,38,0.26)] hover:from-red-500 hover:to-red-700 focus-visible:ring-red-500/35',
        ghost: 'border border-transparent bg-transparent text-stone-700 hover:border-stone-300/80 hover:bg-stone-200/70 hover:text-stone-900 dark:text-zinc-200 dark:hover:border-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-100',
      },
      size: {
        sm: 'h-8 px-3 text-xs',
        md: 'h-9 px-4 py-2',
        lg: 'h-10 px-6 text-[0.95rem]',
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

