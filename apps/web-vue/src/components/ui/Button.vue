<script setup lang="ts">
import { computed } from 'vue'
import { Loader2 } from 'lucide-vue-next'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md border text-sm font-medium shadow-none transition-[background-color,border-color,color] duration-150 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[color:var(--muse-ring)] disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        primary: 'border-[color:var(--muse-accent)] bg-[color:var(--muse-accent)] text-[color:var(--muse-accent-ink)] hover:border-[color:var(--muse-accent-strong)] hover:bg-[color:var(--muse-accent-strong)]',
        secondary: 'border-[color:var(--muse-border)] bg-[color:var(--muse-panel)] text-[color:var(--muse-text)] hover:border-[color:var(--muse-border-strong)] hover:bg-[color:var(--muse-panel-strong)]',
        danger: 'border-[color:var(--muse-danger)] bg-[color:var(--muse-danger)] text-[color:var(--muse-accent-ink)] hover:bg-[#b64a50] hover:border-[#b64a50] dark:hover:bg-[#e07c81] dark:hover:border-[#e07c81]',
        ghost: 'border-transparent bg-transparent text-[color:var(--muse-text-muted)] hover:bg-[color:var(--muse-panel-strong)] hover:text-[color:var(--muse-text)]',
      },
      size: {
        sm: 'h-8 px-3 text-xs',
        md: 'h-10 px-4',
        lg: 'h-11 px-6 text-[0.95rem]',
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
    <Loader2 v-if="loading" class="h-4 w-4 animate-spin" />
    <slot />
  </button>
</template>
