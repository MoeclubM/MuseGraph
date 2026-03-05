<script setup lang="ts">
import { computed } from 'vue'
import { cva } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const props = withDefaults(
  defineProps<{
    modelValue?: unknown
    disabled?: boolean
    error?: string
  }>(),
  {
    modelValue: undefined,
    disabled: false,
    error: '',
  }
)

const emit = defineEmits<{
  'update:modelValue': [value: unknown]
}>()

const selectVariants = cva(
  'h-9 w-full appearance-none rounded-xl border border-stone-300/90 bg-stone-100/92 px-3 pr-9 text-sm text-stone-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)] outline-none transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-800/88 dark:text-zinc-300',
  {
    variants: {
      state: {
        default: 'focus-visible:border-amber-500 focus-visible:ring-[3px] focus-visible:ring-amber-500/35',
        error: 'border-red-500/90 focus-visible:border-red-500 focus-visible:ring-[3px] focus-visible:ring-red-500/30',
      },
    },
    defaultVariants: {
      state: 'default',
    },
  }
)

const classes = computed(() =>
  cn(
    selectVariants({
      state: props.error ? 'error' : 'default',
    })
  )
)

function onChange(e: Event) {
  const target = e.target as HTMLSelectElement
  const option = target.selectedOptions?.[0] as (HTMLOptionElement & { _value?: unknown }) | undefined
  const next = option && Object.prototype.hasOwnProperty.call(option, '_value')
    ? option._value
    : target.value
  emit('update:modelValue', next)
}
</script>

<template>
  <div class="relative">
    <select
      :value="modelValue"
      :disabled="disabled"
      :class="classes"
      @change="onChange"
    >
      <slot />
    </select>
    <svg
      class="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-500 dark:text-zinc-400"
      viewBox="0 0 20 20"
      fill="none"
      aria-hidden="true"
    >
      <path d="M6 8L10 12L14 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    </svg>
  </div>
</template>
